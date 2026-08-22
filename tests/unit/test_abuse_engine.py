"""The deterministic refund-abuse engine: transparent additive score, cited signals, bands."""

from __future__ import annotations

from datetime import date

from disputes_chargebacks_manager.domain.abuse_engine import AbuseEngine, AbusePolicy
from disputes_chargebacks_manager.domain.models import (
    AbuseOutcome,
    CustomerHistory,
    Dispute,
    DisputeTrack,
)

_POLICY = AbusePolicy()


def _dispute(amount_minor: int = 1000) -> Dispute:
    return Dispute(
        id="D1",
        tenant="t",
        track=DisputeTrack.RETAIL,
        reason_code="R-REFUND",
        amount_minor=amount_minor,
        currency="SGD",
        transaction_date=date(2025, 5, 1),
        intake_date=date(2025, 5, 3),
    )


def test_a_clean_history_allows() -> None:
    outcome = AbuseEngine(_POLICY).assess(_dispute(), CustomerHistory())
    assert outcome.outcome is AbuseOutcome.ALLOW
    assert outcome.score == 0
    assert outcome.signals


def test_prior_abuse_plus_velocity_denies() -> None:
    history = CustomerHistory(
        dispute_count_90d=9, prior_abuse_count=1, refund_total_minor_90d=300_000
    )
    outcome = AbuseEngine(_POLICY).assess(_dispute(80_000), history)
    assert outcome.outcome is AbuseOutcome.DENY
    assert outcome.score >= _POLICY.deny_at
    assert len(outcome.citations) == len([s for s in outcome.signals])


def test_the_review_band_is_between_allow_and_deny() -> None:
    # Exactly the velocity signal (2) plus a high amount (1) = 3 = review_at, below deny_at.
    history = CustomerHistory(dispute_count_90d=9)
    outcome = AbuseEngine(_POLICY).assess(_dispute(80_000), history)
    assert outcome.outcome is AbuseOutcome.REVIEW
    assert _POLICY.review_at <= outcome.score < _POLICY.deny_at


def test_the_score_is_a_transparent_sum_a_reviewer_can_reconstruct() -> None:
    history = CustomerHistory(dispute_count_90d=9, prior_abuse_count=1)
    outcome = AbuseEngine(_POLICY).assess(_dispute(80_000), history)
    # velocity(2) + amount(1) + prior_abuse(3) = 6
    assert outcome.score == 6


def test_the_verdict_is_replayable() -> None:
    history = CustomerHistory(dispute_count_90d=9, prior_abuse_count=1)
    a = AbuseEngine(_POLICY).assess(_dispute(80_000), history)
    b = AbuseEngine(_POLICY).assess(_dispute(80_000), history)
    assert a == b
