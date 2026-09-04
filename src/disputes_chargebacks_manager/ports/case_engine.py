"""CaseEnginePort: the boundary onto human-review-console's case spine (open, advance, deadlines).

F2 depends on human-review-console as its case spine (SPEC: F2 slice 2). This port names the
hand-off; the platform adapter drives human-review-console's ``/v1/cases`` open and transition
endpoints with a :class:`~..domain.workflows.WorkflowDefinition` and its ``ClockSpec`` clocks, the
local recording adapter computes the same deadlines from the same clock data offline, and the
on-prem adapter fails fast. The domain stays pure: it hands the engine a dispute and a workflow and
receives a :class:`~..domain.models.CaseHandle`.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..domain.models import CaseHandle, Dispute, DisputeState
from ..domain.workflows import WorkflowDefinition


@runtime_checkable
class CaseEnginePort(Protocol):
    def open_case(
        self, dispute: Dispute, workflow: WorkflowDefinition, *, opened_on: date
    ) -> CaseHandle:
        """Open a case for ``dispute`` on ``workflow`` and return its handle with computed clocks.

        The deadlines are derived from the workflow's ``ClockSpec`` set relative to ``opened_on``,
        so a breach-aged clock is visible immediately. The returned handle's ``state`` is the
        workflow's initial state.
        """
        ...

    def record_transition(
        self, handle: CaseHandle, target: DisputeState, *, trigger: str
    ) -> CaseHandle:
        """Advance an open case to ``target`` and return the updated handle.

        Legality is the caller's to enforce with the deterministic state machine; the engine
        records the move it is given. The returned handle carries the new state and the unchanged
        deadline set.
        """
        ...
