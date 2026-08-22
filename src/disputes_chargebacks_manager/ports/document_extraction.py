"""DocumentExtractionPort: parse chargeback-evidence documents at the edge.

Document AI parses evidence in the managed profile (SPEC: F2 slice 6); the local adapter is a
deterministic stdlib parser over fictional fixtures so the offline gate and the demo run with no
SDK; on-prem fails fast. The extraction is RAW: the engine, not the extractor and not a model,
decides what the fields mean. Every extracted field carries a citation back to the document.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ExtractedEvidence


@runtime_checkable
class DocumentExtractionPort(Protocol):
    def extract_raw(self, content: str, *, doc_type: str, document_id: str) -> ExtractedEvidence:
        """Extract labelled fields from one evidence document, each cited back to the source."""
        ...
