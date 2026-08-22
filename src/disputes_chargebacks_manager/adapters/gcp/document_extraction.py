"""Managed DocumentExtractionPort: Google Document AI (SDK import stays lazy).

The ``google.cloud.documentai`` import lives inside the method, so ``local``/``onprem`` import
this module with no GCP SDK installed. With no SDK reachable the offline parity suite sees the
import fail, which is the honest refusal for a managed adapter called with nothing behind it.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ExtractedEvidence


class CloudDocumentExtractor:
    """Parse evidence documents with Document AI in the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_raw(
        self, content: str, *, doc_type: str, document_id: str
    ) -> ExtractedEvidence:  # pragma: no cover - needs live Document AI
        from google.cloud import documentai

        client = documentai.DocumentProcessorServiceClient()
        raw = documentai.RawDocument(content=content.encode("utf-8"), mime_type="text/plain")
        request = documentai.ProcessRequest(raw_document=raw)
        result = client.process_document(request=request)
        fields = tuple((entity.type_, entity.mention_text) for entity in result.document.entities)
        return ExtractedEvidence(
            document_id=document_id, doc_type=doc_type, fields=fields, citations=()
        )
