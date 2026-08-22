"""On-prem RegulatorResponsePort: fail-fast portability placeholder (P-12).

The client runs its own complaints/regulator-response system on-premises, so this binding refuses
rather than returning a blank draft a caller might treat as complete.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RegulatorDraft


class OnPremRegulatorResponder:
    """Satisfies RegulatorResponsePort but refuses: bind the client's own module on-prem."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_response(
        self, *, dispute_id: str, category: str, redacted_narrative: str
    ) -> RegulatorDraft:
        raise NotImplementedError(
            "on-prem regulator response is a portability placeholder: bind the client's own "
            "complaints module (see docs/onprem-migration.md). A regulatory-track dispute must "
            "still reach a human-reviewed response."
        )
