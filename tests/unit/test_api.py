"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_TOKEN_ENV = "DISPUTES_S2S_TOKEN"

#: An ineligible dispute: filed past the 120-day window, so the deterministic verdict rejects and
#: the rejection is routed (requires_human_review True).
_INELIGIBLE_BODY = {
    "dispute": {
        "id": "DSP-API-1",
        "track": "card_scheme",
        "reason_code": "10.4",
        "amount_minor": 9900,
        "currency": "SGD",
        "transaction_date": "2024-01-01",
        "intake_date": "2025-05-10",
    },
    "as_of": "2025-06-01",
}

#: An eligible dispute: filed within the window, so it advances to evidence review, no rejection.
_ELIGIBLE_BODY = {
    "dispute": {
        "id": "DSP-API-2",
        "track": "card_scheme",
        "reason_code": "10.4",
        "amount_minor": 9900,
        "currency": "SGD",
        "transaction_date": "2025-05-01",
        "intake_date": "2025-05-10",
    },
    "as_of": "2025-06-01",
}


def test_open_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/disputes/open", json=_INELIGIBLE_BODY, headers={"X-Dev-Persona": "auditor"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible"] is False
    assert body["state"] == "rejected"
    assert body["requires_human_review"] is True
    # Rule R8: the rejection was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]


def test_eligible_open_advances_without_review(api_client: TestClient) -> None:
    body = api_client.post(
        "/v1/disputes/open", json=_ELIGIBLE_BODY, headers={"X-Dev-Persona": "auditor"}
    ).json()
    assert body["eligible"] is True
    assert body["state"] == "evidence_review"
    assert body["requires_human_review"] is False
    assert body["review_ref"] == ""
    assert body["deadlines"], "an opened card-scheme case carries its regulatory clocks"


def test_intake_classifies_and_can_fail_closed(api_client: TestClient) -> None:
    body = api_client.post(
        "/v1/intake",
        json={"conversation_ref": "conv-complaint-003"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    # A regulatory complaint never opens a lifecycle case; it routes to human review (R8).
    assert body["category"] == "complaint_regulatory"
    assert body["opened"] is False
    assert body["review_ref"]


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/disputes/open", json=_ELIGIBLE_BODY, headers={"X-Dev-Persona": "ghost"}
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
