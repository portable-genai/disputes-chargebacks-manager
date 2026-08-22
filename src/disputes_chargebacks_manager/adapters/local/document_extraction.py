"""Local DocumentExtractionPort: a deterministic stdlib parser over fictional evidence text.

No Document AI, no SDK. It reads ``key: value`` lines from the supplied text (the shape of the
synthetic fixtures) and returns each as a labelled field cited back to the document line. That is
enough to exercise the representment path offline; the managed adapter swaps in Document AI with
no change above this seam.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.models import ExtractedEvidence


class LocalDocumentExtractor:
    """Parse ``key: value`` evidence lines deterministically for the offline profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_raw(self, content: str, *, doc_type: str, document_id: str) -> ExtractedEvidence:
        fields: list[tuple[str, str]] = []
        citations: list[Citation] = []
        for line_no, raw in enumerate(content.splitlines(), start=1):
            line = raw.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if not key or not value:
                continue
            fields.append((key, value))
            citations.append(
                Citation(
                    source_id=f"{document_id}:L{line_no}",
                    title=f"{doc_type} field: {key}",
                    snippet=line[:80],
                )
            )
        return ExtractedEvidence(
            document_id=document_id,
            doc_type=doc_type,
            fields=tuple(fields),
            citations=tuple(citations),
        )
