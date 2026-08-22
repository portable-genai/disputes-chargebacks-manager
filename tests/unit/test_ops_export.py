"""The ops-worklist export: conforms to the shared contract, with drift guards on both sides.

The contract is authoritatively owned by F1 (recon-breaks-engine); F2 conforms to it. Until
F1 lands in this workspace, ``schema/ops_worklist_export.schema.json`` is F2's local copy of that
contract, and these tests are the drift guard: the built export validates against the enums the
schema declares (read FROM the file, so the test cannot silently agree with a stale schema), the
aging buckets and clock states are exhaustive, and the export replays byte-for-byte.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from disputes_chargebacks_manager.domain.kernel import Severity
from disputes_chargebacks_manager.domain.models import DisputeState, IntakeCategory
from disputes_chargebacks_manager.domain.ops_export import (
    aging_bucket,
    build_export,
    build_row,
    clock_state,
)

from tests import REPO_ROOT
from tests.fixtures import sample_cases

_SCHEMA = json.loads(
    (Path(REPO_ROOT) / "schema" / "ops_worklist_export.schema.json").read_text(encoding="utf-8")
)
_ROW_DEF = _SCHEMA["definitions"]["row"]["properties"]
_AS_OF = date(2025, 6, 1)


def _row(state: DisputeState = DisputeState.EVIDENCE_REVIEW) -> dict[str, object]:
    return build_row(
        sample_cases.ELIGIBLE_DISPUTE,
        state=state,
        severity=Severity.MEDIUM,
        category=IntakeCategory.CARD_UNAUTHORISED,
        eligibility=None,
        as_of=_AS_OF,
    )


def test_a_row_has_exactly_the_contract_fields() -> None:
    row = _row()
    required = set(_SCHEMA["definitions"]["row"]["required"])
    assert required <= set(row), f"row is missing contract fields: {required - set(row)}"
    # The signal extension is present and carries the declared keys.
    signal_required = set(_SCHEMA["definitions"]["complaint_signal"]["required"])
    assert signal_required <= set(row["signal"])  # type: ignore[arg-type]


def test_aging_bucket_only_emits_declared_labels() -> None:
    declared = set(_ROW_DEF["aging_bucket"]["enum"])
    for age in (0, 3, 4, 7, 8, 14, 15, 30, 31, 400):
        assert aging_bucket(age) in declared


def test_clock_state_only_emits_declared_labels() -> None:
    declared = set(_ROW_DEF["sla_clock"]["enum"])
    for days in (None, -5, 0, 1, 2, 3, 100):
        assert clock_state(days_to_deadline=days) in declared


def test_a_breached_deadline_reads_breached() -> None:
    assert clock_state(days_to_deadline=-1) == "breached"
    assert clock_state(days_to_deadline=1) == "due_soon"
    assert clock_state(days_to_deadline=10) == "on_track"
    assert clock_state(days_to_deadline=None) == "none"


def test_a_terminal_row_reports_no_live_clock() -> None:
    row = _row(state=DisputeState.CLOSED_WON)
    assert row["sla_clock"] == "none"
    assert row["signal"]["clock_state"] == "none"  # type: ignore[index]


def test_the_export_envelope_is_versioned_and_replayable() -> None:
    rows = (_row(),)
    a = build_export(rows, as_of=_AS_OF)
    b = build_export(rows, as_of=_AS_OF)
    assert a == b
    assert a["contract_version"] == _SCHEMA["properties"]["contract_version"]["const"]
    assert a["feed_id"]
    assert a["as_of"] == _AS_OF.isoformat()


def test_the_severity_and_category_values_are_taken_from_the_engine_enums() -> None:
    row = build_row(
        sample_cases.ELIGIBLE_DISPUTE,
        state=DisputeState.EVIDENCE_REVIEW,
        severity=Severity.HIGH,
        category=IntakeCategory.RETAIL_REFUND,
        eligibility=None,
        as_of=_AS_OF,
    )
    signal = row["signal"]
    assert signal["severity"] == "high"  # type: ignore[index]
    assert signal["category"] == "retail_refund"  # type: ignore[index]
