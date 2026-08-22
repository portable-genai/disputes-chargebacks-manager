"""On-prem DocumentExtractionPort: fail-fast portability placeholder (P-12).

The client runs its own document-understanding stack on-premises, so this binding refuses rather
than returning empty fields that a downstream engine would read as "no evidence".
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ExtractedEvidence


class OnPremDocumentExtractor:
    """Satisfies DocumentExtractionPort but refuses: bind the client's own parser on-prem."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_raw(self, content: str, *, doc_type: str, document_id: str) -> ExtractedEvidence:
        raise NotImplementedError(
            "on-prem document extraction is a portability placeholder: bind the client's own "
            "document-understanding stack (see docs/onprem-migration.md)."
        )
