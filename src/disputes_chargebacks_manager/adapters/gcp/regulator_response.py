"""Managed RegulatorResponsePort: call complaints-review's A2A tools over S2S (no cloud SDK).

complaints-review (complaints-review) stays its own repo and remains authoritative for
regulator-response drafting; this adapter reaches it over HTTPS with stdlib ``urllib``, so it
imports with no GCP SDK. It FAILS CLOSED when ``doc6_url`` is unset: a regulatory-track dispute
must not silently skip the regulator-response module. That refusal is what the offline parity
suite observes. The live A2A call is exercised against a running complaints-review in integration.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RegulatorDraft


class CloudRegulatorResponder:
    """Delegate regulator-response drafting to complaints-review's A2A
    tools (rule R8 review-gated).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_response(
        self, *, dispute_id: str, category: str, redacted_narrative: str
    ) -> RegulatorDraft:
        base = self._settings.doc6_url.strip()
        if not base:
            raise RuntimeError(
                "doc6_url is not configured, so the complaints-review regulator-response module is "
                "unreachable. Set DOC6_A2A_URL (config/settings.yaml doc6_url); a "
                "regulatory-track dispute must reach the regulator-response module."
            )
        return self._call_doc6(base.rstrip("/"), dispute_id, category, redacted_narrative)

    def _call_doc6(
        self, base: str, dispute_id: str, category: str, redacted_narrative: str
    ) -> RegulatorDraft:  # pragma: no cover - needs live complaints-review
        import json
        import urllib.request

        from ...domain.kernel import Citation

        payload = json.dumps(
            {"tool": "draft_response", "narrative": redacted_narrative, "product": category}
        ).encode("utf-8")
        request = urllib.request.Request(f"{base}/a2a/tools", data=payload, method="POST")
        request.add_header("content-type", "application/json")
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
        return RegulatorDraft(
            dispute_id=dispute_id,
            draft_text=str(body.get("draft", "")),
            category=category,
            requires_human_review=True,
            citations=(
                Citation(
                    source_id=f"doc6:{dispute_id}",
                    title="complaints-review regulator draft",
                    snippet=category,
                ),
            ),
        )
