"""Rule R8: a consequential disposition is ROUTED to Hrz7, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
a consequential disposition produces an outbound review, a non-consequential one produces none,
the payload leaves redacted, and the on-prem placeholder refuses rather than swallowing it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from disputes_chargebacks_manager.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from disputes_chargebacks_manager.adapters.local.review_router import (
    LocalReviewRouter,
)
from disputes_chargebacks_manager.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from disputes_chargebacks_manager.api.app import (
    app,
)
from disputes_chargebacks_manager.config import (
    Settings,
    build_container,
    build_service,
)
from disputes_chargebacks_manager.domain.kernel import Severity
from disputes_chargebacks_manager.domain.models import CustomerHistory, DisputeDisposition

from tests.fixtures import sample_cases

_MAKER = "analyst@bank.example"

#: An ineligible open-dispute body: the reason code is filed past its window, so the deterministic
#: verdict is INELIGIBLE and the rejection is routed.
_OPEN_BODY = {
    "dispute": {
        "id": "DSP-R8",
        "track": "card_scheme",
        "reason_code": "10.4",
        "amount_minor": 9900,
        "currency": "SGD",
        "transaction_date": "2024-01-01",
        "intake_date": "2025-05-10",
    },
    "as_of": "2025-06-01",
}

#: An eligible body: the deterministic verdict is ELIGIBLE, so nothing is routed.
_ELIGIBLE_BODY = {
    "dispute": {
        "id": "DSP-OK",
        "track": "card_scheme",
        "reason_code": "10.4",
        "amount_minor": 9900,
        "currency": "SGD",
        "transaction_date": "2025-05-01",
        "intake_date": "2025-05-10",
    },
    "as_of": "2025-06-01",
}


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _deny_disposition() -> DisputeDisposition:
    """A DENY abuse disposition (CRITICAL) built through the real deterministic engine path."""
    service = build_service(build_container(_settings()))
    decision = service.assess_abuse(
        sample_cases.ABUSE_DISPUTE, sample_cases.ABUSIVE_HISTORY, actor=_MAKER
    )
    assert decision.disposition is not None
    return decision.disposition


def test_a_consequential_disposition_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(sample_cases.CANONICAL_DISPOSITION, maker=_MAKER)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == _MAKER
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.HIGH.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_critical_disposition_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    router.route(_deny_disposition(), maker=_MAKER)
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """Hrz7 is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    disposition = DisputeDisposition(
        subject=sample_cases.PII_DISPUTE.id,
        severity=Severity.HIGH,
        decision=sample_cases.CANONICAL_DISPOSITION.decision,
        summary=f"NRIC {sample_cases.PLANTED_NRIC} rejection requires sign-off",
        requires_human_review=True,
        dispute_id=sample_cases.PII_DISPUTE.id,
    )
    router.route(disposition, maker=_MAKER)
    wire = repr(router.outbox.pending()[0].review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """A disposition with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(sample_cases.CANONICAL_DISPOSITION, maker=_MAKER)


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.CANONICAL_DISPOSITION, maker=_MAKER)


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: a rejection must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    ineligible = client.post(
        "/v1/disputes/open", json=_OPEN_BODY, headers={"X-Dev-Persona": "auditor"}
    ).json()
    assert ineligible["requires_human_review"] is True
    assert ineligible["review_ref"], "an ineligible rejection was not routed"

    eligible = client.post(
        "/v1/disputes/open", json=_ELIGIBLE_BODY, headers={"X-Dev-Persona": "auditor"}
    ).json()
    assert eligible["requires_human_review"] is False
    assert eligible["review_ref"] == "", "an eligible open must not manufacture a review"


def test_a_clean_abuse_assessment_is_not_routed() -> None:
    """The negative control: an ALLOW verdict has no disposition and nothing is routed."""
    service = build_service(build_container(_settings()))
    decision = service.assess_abuse(sample_cases.CLEAN_DISPUTE, CustomerHistory(), actor=_MAKER)
    assert decision.disposition is None
    assert decision.review_ref == ""
