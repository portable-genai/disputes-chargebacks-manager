"""On-prem CaseEnginePort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The client runs its own case-management spine on-premises, so this binding refuses at call time
rather than opening a case nowhere. Refusing is the correct failure: a silent success would
convert an escalation into an unreviewed, un-tracked one.
"""

from __future__ import annotations

from datetime import date

from ...config import Settings
from ...domain.models import CaseHandle, Dispute, DisputeState
from ...domain.workflows import WorkflowDefinition


class OnPremCaseEngine:
    """Satisfies CaseEnginePort but refuses: bind the client's own case spine on-prem."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def open_case(
        self, dispute: Dispute, workflow: WorkflowDefinition, *, opened_on: date
    ) -> CaseHandle:
        raise NotImplementedError(
            "on-prem case engine is a portability placeholder: bind the client's own case "
            "spine (see docs/onprem-migration.md). A dispute must not be opened with no case."
        )

    def record_transition(
        self, handle: CaseHandle, target: DisputeState, *, trigger: str
    ) -> CaseHandle:
        raise NotImplementedError(
            "on-prem case engine is a portability placeholder: bind the client's own case spine."
        )
