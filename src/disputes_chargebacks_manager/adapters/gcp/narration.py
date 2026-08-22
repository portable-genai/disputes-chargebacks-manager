"""Managed NarrationPort: Vertex AI (SDK import stays lazy).

The ``google.cloud.aiplatform`` import lives inside each method, so the offline profiles import
this module with no GCP SDK present and the parity suite sees the import fail when nothing is
reachable. The model's output is validated and discarded on failure by the CALLER; this adapter
only carries the request.
"""

from __future__ import annotations

from ...config import Settings


class CloudNarrator:
    """Classify and narrate with a Vertex model in the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _model(self) -> object:  # pragma: no cover - needs live Vertex
        from google.cloud import aiplatform

        aiplatform.init(location=self._settings.region)
        return aiplatform.gapic.PredictionServiceClient()

    def classify(
        self, text: str, *, categories: tuple[str, ...]
    ) -> str:  # pragma: no cover - needs live Vertex
        self._model()
        raise RuntimeError("live Vertex classification is wired in deployment, not the gate")

    def narrate(
        self, *, instruction: str, facts: tuple[tuple[str, str], ...]
    ) -> str:  # pragma: no cover - needs live Vertex
        self._model()
        raise RuntimeError("live Vertex narration is wired in deployment, not the gate")
