"""Local CaseEnginePort: compute case deadlines from the workflow clocks, no live Hrz7.

The offline recording adapter for the case spine. It opens a case by deriving each deadline from
the workflow's ``ClockSpec`` set relative to the open date, using the SAME clock data the managed
adapter hands Hrz7, so a golden journey's clock breaches are reproducible offline. It records the
state it is moved to; legality is the state machine's job, asserted by the caller.
"""

from __future__ import annotations

from datetime import date, timedelta

from ...config import Settings
from ...domain.models import CaseDeadline, CaseHandle, Dispute, DisputeState
from ...domain.workflows import WorkflowDefinition


class LocalCaseEngine:
    """Deterministic, SDK-free case recorder for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def open_case(
        self, dispute: Dispute, workflow: WorkflowDefinition, *, opened_on: date
    ) -> CaseHandle:
        deadlines = tuple(
            CaseDeadline(
                name=clock.name,
                due=opened_on + timedelta(days=clock.days),
                regulatory=clock.regulatory,
            )
            for clock in workflow.clocks
        )
        return CaseHandle(
            case_id=f"case-{dispute.id}",
            dispute_id=dispute.id,
            state=workflow.initial,
            deadlines=deadlines,
        )

    def record_transition(
        self, handle: CaseHandle, target: DisputeState, *, trigger: str
    ) -> CaseHandle:
        return CaseHandle(
            case_id=handle.case_id,
            dispute_id=handle.dispute_id,
            state=target,
            deadlines=handle.deadlines,
        )
