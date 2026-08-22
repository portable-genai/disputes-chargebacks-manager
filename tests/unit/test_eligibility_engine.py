"""The deterministic reason-code eligibility engine: windows, fail-closed, cited reasoning."""

from __future__ import annotations

from datetime import date

import pytest

from disputes_chargebacks_manager.domain.eligibility_engine import (
    EligibilityEngine,
    UnknownTrackError,
)
from disputes_chargebacks_manager.domain.models import Dispute, DisputeTrack
from disputes_chargebacks_manager.domain.policy_defaults import DEFAULT_REASON_CODE_PACKS

_AS_OF = date(2025, 6, 1)


def _engine() -> EligibilityEngine:
    return EligibilityEngine(DEFAULT_REASON_CODE_PACKS)


def _dispute(*, reason: str, txn: date, intake: date, track: DisputeTrack) -> Dispute:
    return Dispute(
        id="D1",
        tenant="t",
        track=track,
        reason_code=reason,
        amount_minor=1000,
        currency="SGD",
        transaction_date=txn,
        intake_date=intake,
    )


def test_within_window_is_eligible_and_carries_a_deadline() -> None:
    outcome = _engine().assess(
        _dispute(
            reason="10.4",
            txn=date(2025, 5, 1),
            intake=date(2025, 5, 10),
            track=DisputeTrack.CARD_SCHEME,
        ),
        as_of=_AS_OF,
    )
    assert outcome.eligible is True
    assert outcome.response_deadline == date(2025, 5, 30)  # intake + 20 days
    assert outcome.citations, "an eligibility verdict must cite the pack rule"


def test_past_the_window_is_ineligible() -> None:
    outcome = _engine().assess(
        _dispute(
            reason="10.4",
            txn=date(2024, 1, 1),
            intake=date(2025, 5, 10),
            track=DisputeTrack.CARD_SCHEME,
        ),
        as_of=_AS_OF,
    )
    assert outcome.eligible is False
    assert outcome.response_deadline is None
    assert any("window" in r for r in outcome.reasons)


def test_an_unknown_reason_code_fails_closed_not_open() -> None:
    outcome = _engine().assess(
        _dispute(
            reason="99.9",
            txn=date(2025, 5, 1),
            intake=date(2025, 5, 10),
            track=DisputeTrack.CARD_SCHEME,
        ),
        as_of=_AS_OF,
    )
    assert outcome.eligible is False
    assert any("unknown" in r.lower() or "not in" in r.lower() for r in outcome.reasons)


def test_intake_before_transaction_is_impossible_and_ineligible() -> None:
    outcome = _engine().assess(
        _dispute(
            reason="R-REFUND",
            txn=date(2025, 5, 10),
            intake=date(2025, 5, 1),
            track=DisputeTrack.RETAIL,
        ),
        as_of=_AS_OF,
    )
    assert outcome.eligible is False


def test_an_unregistered_track_raises_rather_than_defaulting() -> None:
    engine = EligibilityEngine((DEFAULT_REASON_CODE_PACKS[0],))  # card only
    with pytest.raises(UnknownTrackError):
        engine.assess(
            _dispute(
                reason="R-REFUND",
                txn=date(2025, 5, 1),
                intake=date(2025, 5, 10),
                track=DisputeTrack.RETAIL,
            ),
            as_of=_AS_OF,
        )


def test_the_verdict_is_replayable_byte_for_byte() -> None:
    dispute = _dispute(
        reason="13.1", txn=date(2025, 5, 1), intake=date(2025, 5, 3), track=DisputeTrack.CARD_SCHEME
    )
    a = _engine().assess(dispute, as_of=_AS_OF)
    b = _engine().assess(dispute, as_of=_AS_OF)
    assert a == b
