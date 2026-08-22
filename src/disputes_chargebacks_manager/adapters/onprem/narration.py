"""On-prem NarrationPort: fail-fast portability placeholder (P-12).

The client runs its own model gateway on-premises, so this binding refuses rather than returning
a blank string a caller might narrate into a document.
"""

from __future__ import annotations

from ...config import Settings


class OnPremNarrator:
    """Satisfies NarrationPort but refuses: bind the client's own model gateway on-prem."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(self, text: str, *, categories: tuple[str, ...]) -> str:
        raise NotImplementedError(
            "on-prem narration is a portability placeholder: bind the client's own model "
            "gateway (see docs/onprem-migration.md)."
        )

    def narrate(self, *, instruction: str, facts: tuple[tuple[str, str], ...]) -> str:
        raise NotImplementedError(
            "on-prem narration is a portability placeholder: bind the client's own model gateway."
        )
