"""RegulatorResponsePort: the boundary onto complaints-review, which joins as the regulator-response
module.

When a dispute is on the regulatory-complaint track, complaints-review (complaints-review) remains
authoritative for drafting the regulator response (SPEC: F2 slice 7; the durable boundary in
plan-repo-merges.md). The platform adapter calls complaints-review's A2A tools with the REDACTED
extract; the local adapter returns a canned cited draft so the flow is demoable offline; on-prem
fails fast. complaints-review stays its own repo; this port is the only coupling.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RegulatorDraft


@runtime_checkable
class RegulatorResponsePort(Protocol):
    def draft_response(
        self, *, dispute_id: str, category: str, redacted_narrative: str
    ) -> RegulatorDraft:
        """Draft a regulator response for a complaint-track dispute, always review-gated.

        ``redacted_narrative`` is already PII-masked by the caller: no raw identifier crosses this
        boundary to complaints-review. The returned draft carries ``requires_human_review=True`` and
        citations.
        """
        ...
