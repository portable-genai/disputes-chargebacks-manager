"""Managed CaseEnginePort: drive human-review-console's ``/v1/cases`` spine over S2S (no cloud SDK).

The case spine is human-review-console, reached over HTTPS, so this adapter uses stdlib ``urllib``
(like the review kit) rather than a cloud SDK: it imports cleanly with no GCP SDK present. It FAILS
CLOSED when ``case_url`` is unset, because an escalation with no case spine must not be silently
dropped; that refusal is what the offline parity suite observes. The live open/transition calls are
exercised against a running human-review-console in integration, not in the SDK-free gate.
"""

from __future__ import annotations

from datetime import date, timedelta

from ...config import Settings
from ...domain.models import CaseDeadline, CaseHandle, Dispute, DisputeState
from ...domain.workflows import WorkflowDefinition


class CloudCaseEngine:
    """Open and advance cases on the human-review-console case spine (rule R8 case backbone)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _base_url(self) -> str:
        base = self._settings.case_url.strip()
        if not base:
            raise RuntimeError(
                "case_url is not configured, so the human-review-console case spine is "
                "unreachable. Set "
                "HUMAN_REVIEW_URL / the case endpoint (config/settings.yaml case_url); an "
                "escalation must not be opened with no case behind it."
            )
        return base.rstrip("/")

    def open_case(
        self, dispute: Dispute, workflow: WorkflowDefinition, *, opened_on: date
    ) -> CaseHandle:
        base = self._base_url()
        deadlines = tuple(
            CaseDeadline(clock.name, opened_on + timedelta(days=clock.days), clock.regulatory)
            for clock in workflow.clocks
        )
        return self._post_open(base, dispute, workflow, deadlines)

    def record_transition(
        self, handle: CaseHandle, target: DisputeState, *, trigger: str
    ) -> CaseHandle:
        base = self._base_url()
        return self._post_transition(base, handle, target, trigger)

    def _post_open(
        self,
        base: str,
        dispute: Dispute,
        workflow: WorkflowDefinition,
        deadlines: tuple[CaseDeadline, ...],
    ) -> CaseHandle:  # pragma: no cover - needs live human-review-console
        import json
        import urllib.request

        payload = json.dumps(
            {
                "workflow": workflow.track.value,
                "subject": dispute.id,
                "tenant": dispute.tenant,
            }
        ).encode("utf-8")
        request = urllib.request.Request(f"{base}/v1/cases", data=payload, method="POST")
        request.add_header("content-type", "application/json")
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
        return CaseHandle(
            case_id=str(body.get("case_id", f"case-{dispute.id}")),
            dispute_id=dispute.id,
            state=workflow.initial,
            deadlines=deadlines,
        )

    def _post_transition(
        self, base: str, handle: CaseHandle, target: DisputeState, trigger: str
    ) -> CaseHandle:  # pragma: no cover - needs live human-review-console
        import json
        import urllib.request

        payload = json.dumps({"trigger": trigger, "target": target.value}).encode("utf-8")
        url = f"{base}/v1/cases/{handle.case_id}/transition"
        request = urllib.request.Request(url, data=payload, method="POST")
        request.add_header("content-type", "application/json")
        with urllib.request.urlopen(request, timeout=10):
            pass
        return CaseHandle(handle.case_id, handle.dispute_id, target, handle.deadlines)
