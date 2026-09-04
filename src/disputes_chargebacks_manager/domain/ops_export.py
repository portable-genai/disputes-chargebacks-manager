"""Deterministic ops-worklist export: the cross-repo contract F5 consumes, F2 conforms to.

The shared data contract (SPEC, "Shared across the wave") is authoritatively owned by F1; this
module produces rows in that shape plus a backward-compatible ``signal`` extension carrying the
deterministic intake signal consumer-duty-monitoring reads (category, product, market, severity,
eligibility, clock state). It is PURE: every field is computed from engine outputs with an explicit
``as_of``, and ``tests/unit/test_ops_export.py`` validates each built document against
``schema/ops_worklist_export.schema.json`` and drift-guards the aging buckets and clock states.

Nothing here writes to a warehouse: the BigQuery export adapter is a per-deployment concern. This
builder is what that adapter (or the CLI/API) serialises, so the SHAPE is proved offline.
"""

from __future__ import annotations

from datetime import date

from .kernel import Severity
from .models import (
    Dispute,
    DisputeState,
    EligibilityOutcome,
    IntakeCategory,
)

CONTRACT_VERSION = "1"
FEED_ID = "f2.disputes.worklist"

_TERMINAL_STATES = frozenset(
    {
        DisputeState.CLOSED_WON,
        DisputeState.CLOSED_LOST,
        DisputeState.CLOSED_ABUSE,
        DisputeState.REJECTED,
    }
)


def aging_bucket(age_days: int) -> str:
    """Map an integer age in days to the contract's fixed bucket labels (drift-guarded)."""
    if age_days <= 3:
        return "0-3d"
    if age_days <= 7:
        return "4-7d"
    if age_days <= 14:
        return "8-14d"
    if age_days <= 30:
        return "15-30d"
    return "30d+"


def clock_state(*, days_to_deadline: int | None) -> str:
    """The SLA-clock state for a row: on_track / due_soon / breached / none.

    ``None`` (no deadline, e.g. an ineligible or closed item) is ``none``. A deadline already
    passed is ``breached``; within two days is ``due_soon``; otherwise ``on_track``.
    """
    if days_to_deadline is None:
        return "none"
    if days_to_deadline < 0:
        return "breached"
    if days_to_deadline <= 2:
        return "due_soon"
    return "on_track"


def _eligibility_label(eligibility: EligibilityOutcome | None) -> str:
    if eligibility is None:
        return "unknown"
    return "eligible" if eligibility.eligible else "ineligible"


def build_row(
    dispute: Dispute,
    *,
    state: DisputeState,
    severity: Severity,
    category: IntakeCategory,
    eligibility: EligibilityOutcome | None,
    as_of: date,
    closed_today: int = 0,
) -> dict[str, object]:
    """Build one contract row for a dispute, with the complaint-signal extension.

    ``age_days`` is measured from intake to ``as_of`` and floored at zero. The clock is derived
    from the eligibility response deadline when one exists, so a terminal or ineligible item
    reports ``none`` rather than a stale countdown.
    """
    age_days = max(0, (as_of - dispute.intake_date).days)
    if eligibility is not None and eligibility.response_deadline is not None:
        days_to_deadline: int | None = (eligibility.response_deadline - as_of).days
    else:
        days_to_deadline = None
    if state in _TERMINAL_STATES:
        days_to_deadline = None
    state_clock = clock_state(days_to_deadline=days_to_deadline)
    return {
        "item_id": dispute.id,
        "tenant": dispute.tenant,
        "queue": dispute.track.value,
        "state": state.value,
        "age_days": age_days,
        "aging_bucket": aging_bucket(age_days),
        "sla_clock": state_clock,
        "amount_minor": dispute.amount_minor,
        "currency": dispute.currency,
        "throughput_closed_today": closed_today,
        "signal": {
            "category": category.value,
            "product": dispute.product,
            "market": dispute.market,
            "severity": severity.value,
            "eligibility": _eligibility_label(eligibility),
            "clock_state": state_clock,
        },
    }


def build_export(rows: tuple[dict[str, object], ...], *, as_of: date) -> dict[str, object]:
    """Wrap rows in the versioned contract envelope the control room consumes."""
    return {
        "contract_version": CONTRACT_VERSION,
        "feed_id": FEED_ID,
        "as_of": as_of.isoformat(),
        "rows": list(rows),
    }
