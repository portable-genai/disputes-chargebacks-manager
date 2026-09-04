"""Local RegulatorResponsePort: a canned, cited regulator draft (no live complaints-review).

Stands in for complaints-review's A2A drafting offline so the regulatory-complaint path is demoable.
It stamps the draft marker and always sets ``requires_human_review``: a regulator response is never
sent by the system. The managed adapter replaces this with a call to complaints-review's own tools;
the boundary and the review gate are identical.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.models import RegulatorDraft

_DRAFT_MARKER = "[DRAFT - regulator response, requires review]"


class LocalRegulatorResponder:
    """Return a canned cited draft for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_response(
        self, *, dispute_id: str, category: str, redacted_narrative: str
    ) -> RegulatorDraft:
        body = (
            f"{_DRAFT_MARKER}\n"
            f"Re: complaint {dispute_id} ({category}).\n"
            "We acknowledge the complaint and have opened a formal review. The account narrative "
            f"on file reads: {redacted_narrative}. A substantive response will follow within the "
            "regulatory window."
        )
        return RegulatorDraft(
            dispute_id=dispute_id,
            draft_text=body,
            category=category,
            requires_human_review=True,
            citations=(
                Citation(
                    source_id=f"doc6:local:{dispute_id}",
                    title="Regulator-response draft (complaints-review module, offline stand-in)",
                    snippet=category,
                ),
            ),
        )
