"""Review routing has a switch, default on, and every caller says what happened to a hand-off.

The fleet's runtime-control contract (2026-09-24). Review routing is the one cheap runtime
control this service has: ``DISPUTES_REVIEW_ROUTING`` is read in three states; off binds a
disabled router and says so at startup; on under the managed profile refuses to boot without a
console; and the three routed paths (open, abuse, intake) report ``review_routing`` on the API,
the agent tools and the CLI rather than failing an already-decided outcome when the console is
unreachable. Routing runs inside the domain service, so each surface passes its own recorder in
through ``config.build_service``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from disputes_chargebacks_manager.adapters.controls import (
    DisabledReviewRouter,
    RecordingReviewRouter,
    ReviewRouting,
)
from disputes_chargebacks_manager.agent import tools
from disputes_chargebacks_manager.cli.main import main as cli_main
from disputes_chargebacks_manager.config import (
    REVIEW_ROUTING_ENV,
    Container,
    ControlSwitches,
    ProfileChoice,
    Settings,
    build_container,
    warn_switched_off,
)
from disputes_chargebacks_manager.domain.models import DisputeDisposition
from disputes_chargebacks_manager.envread import ConfiguredEmptyError

from tests.conftest import LOOPBACK_PEER, local_settings, reimport
from tests.fixtures import sample_cases

_AUDITOR = {"X-Dev-Persona": "auditor"}
_LOCAL_ROUTE = "disputes_chargebacks_manager.adapters.local.review_router.LocalReviewRouter.route"
_ESCALATED = sample_cases.CANONICAL_DISPOSITION

#: Filed long after the transaction, so eligibility rejects it and the rejection routes (R8).
_INELIGIBLE = {
    "id": "DSP-SW-1",
    "track": "card_scheme",
    "reason_code": "10.4",
    "amount_minor": 9900,
    "currency": "SGD",
    "transaction_date": "2024-01-01",
    "intake_date": "2025-05-10",
}
_ELIGIBLE = {**_INELIGIBLE, "id": "DSP-SW-2", "transaction_date": "2025-05-01"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REVIEW_ROUTING_ENV, raising=False)
    monkeypatch.delenv("HUMAN_REVIEW_URL", raising=False)


def _client() -> TestClient:
    """A fresh local app, so its per-process container reads this test's posture."""
    return TestClient(reimport("disputes_chargebacks_manager.api.app").app, client=LOOPBACK_PEER)


def _managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "disputes_chargebacks_manager.config.resolve_profile",
        lambda environ=None: ProfileChoice(profile="gcp", explicit=True),
    )


class _Accepting:
    def route(self, result: DisputeDisposition, *, maker: str, tenant: str = "") -> str:
        return "review-1"


class _Refusing:
    def route(self, result: DisputeDisposition, *, maker: str, tenant: str = "") -> str:
        raise ConnectionError("console unreachable")


# --------------------------------------------------------------------------- #
# Three states
# --------------------------------------------------------------------------- #
def test_routing_is_on_when_nothing_is_said() -> None:
    assert Settings.load().controls == ControlSwitches(review_routing=True)


def test_routing_switched_off_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert Settings.load().controls.switched_off() == (REVIEW_ROUTING_ENV,)


def test_an_emptied_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "")
    with pytest.raises(ConfiguredEmptyError, match=REVIEW_ROUTING_ENV):
        Settings.load()


def test_an_unrecognised_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "sometimes")
    with pytest.raises(ValueError, match=REVIEW_ROUTING_ENV):
        Settings.load()


# --------------------------------------------------------------------------- #
# Off binds the disabled router, and says so once
# --------------------------------------------------------------------------- #
def test_off_binds_the_disabled_router() -> None:
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    assert isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_on_binds_the_profile_router() -> None:
    assert not isinstance(Container(local_settings()).review_router, DisabledReviewRouter)


def test_the_off_posture_is_logged_once_however_many_containers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_switched_off.cache_clear()
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    with caplog.at_level(logging.WARNING, logger="disputes_chargebacks_manager.config"):
        for _ in range(3):
            build_container(settings)
    assert caplog.text.count(REVIEW_ROUTING_ENV) == 1


# --------------------------------------------------------------------------- #
# On has to work: checked at boot under the managed profile
# --------------------------------------------------------------------------- #
def test_routing_on_under_gcp_without_a_console_refuses_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)
    with pytest.raises(ConfiguredEmptyError, match="HUMAN_REVIEW_URL"):
        Settings.load()


def test_routing_stated_off_under_gcp_needs_no_console(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "false")
    assert Settings.load().controls.review_routing is False


def test_routing_on_under_gcp_with_a_console_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv("HUMAN_REVIEW_URL", "https://review.example.test")
    assert Settings.load().review_url == "https://review.example.test"


# --------------------------------------------------------------------------- #
# The four routing outcomes
# --------------------------------------------------------------------------- #
def test_routing_outcomes_take_each_of_their_four_values() -> None:
    assert RecordingReviewRouter(_Accepting()).outcome is ReviewRouting.NOT_REQUIRED

    routed = RecordingReviewRouter(_Accepting())
    assert routed.route(_ESCALATED, maker="m") == "review-1"
    assert routed.outcome is ReviewRouting.ROUTED

    off = RecordingReviewRouter(DisabledReviewRouter(local_settings()))
    assert off.route(_ESCALATED, maker="m") == ""
    assert off.outcome is ReviewRouting.OFF

    failed = RecordingReviewRouter(_Refusing())
    assert failed.route(_ESCALATED, maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED


def test_a_failed_hand_off_is_reported_and_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = RecordingReviewRouter(_Refusing())
    with caplog.at_level(logging.WARNING, logger="disputes_chargebacks_manager.adapters.controls"):
        assert failed.route(_ESCALATED, maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED
    assert "ConnectionError" in caplog.text


# --------------------------------------------------------------------------- #
# Every caller reports it: the API, the agent tools, the CLI
# --------------------------------------------------------------------------- #
def _open(client: TestClient, dispute: dict[str, Any] = _INELIGIBLE) -> Any:
    body = {"dispute": dispute, "as_of": "2025-06-01"}
    return client.post("/v1/disputes/open", json=body, headers=_AUDITOR)


def _routed_calls(client: TestClient) -> list[Any]:
    history = {"dispute_count_90d": 9, "prior_abuse_count": 3, "refund_total_minor_90d": 900000}
    return [
        _open(client),
        client.post(
            "/v1/disputes/abuse",
            json={"dispute": _INELIGIBLE, "history": history},
            headers=_AUDITOR,
        ),
        client.post(
            "/v1/intake", json={"conversation_ref": "conv-complaint-003"}, headers=_AUDITOR
        ),
    ]


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with _client() as c:
        yield c


def test_the_api_reports_a_routed_hand_off_on_every_routed_path(client: TestClient) -> None:
    for response in _routed_calls(client):
        body = response.json()
        assert body["requires_human_review"] is True, body
        assert body["review_routing"] == "routed"
        assert body["review_ref"]


def test_the_api_reports_nothing_to_route(client: TestClient) -> None:
    body = _open(client, _ELIGIBLE).json()
    assert body["requires_human_review"] is False
    assert body["review_routing"] == "not_required"


def test_the_api_reports_routing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    with _client() as client:
        for response in _routed_calls(client):
            assert response.json()["review_routing"] == "off"
            assert response.json()["review_ref"] == ""


def test_the_api_reports_a_failed_hand_off_instead_of_failing_the_request(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    for response in _routed_calls(client):
        assert response.status_code == 200
        assert response.json()["review_routing"] == "failed"
        assert response.json()["review_ref"] == ""


def test_the_agent_tools_report_the_hand_off(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = local_settings()
    dispute = {
        "dispute_id": _INELIGIBLE["id"],
        "track": _INELIGIBLE["track"],
        "reason_code": _INELIGIBLE["reason_code"],
        "amount_minor": _INELIGIBLE["amount_minor"],
        "currency": _INELIGIBLE["currency"],
        "transaction_date": _INELIGIBLE["transaction_date"],
        "intake_date": _INELIGIBLE["intake_date"],
    }
    opened = tools.open_dispute(**dispute, as_of="2025-06-01", settings=settings)
    assert opened["review_routing"] == "routed"

    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    abuse = tools.assess_refund_abuse(
        **dispute, dispute_count_90d=9, prior_abuse_count=3, settings=settings
    )
    assert abuse["review_routing"] == "failed"
    assert abuse["review_ref"] == ""
    intake = tools.classify_intake("conv-complaint-003", settings=settings)
    assert intake["review_routing"] == "failed"


def test_the_cli_reports_the_hand_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [_INELIGIBLE[k] for k in ("id", "track", "reason_code")]
    args += [str(_INELIGIBLE["amount_minor"]), _INELIGIBLE["currency"]]
    args += [_INELIGIBLE["transaction_date"], _INELIGIBLE["intake_date"]]
    assert cli_main(["open", *args, "--as-of", "2025-06-01"]) == 0
    assert "human review hand-off : routed" in capsys.readouterr().out

    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    assert cli_main(["intake", "conv-complaint-003"]) == 0
    assert "human review hand-off : failed" in capsys.readouterr().out
