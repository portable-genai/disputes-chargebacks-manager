"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table and
the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from disputes_chargebacks_manager.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from disputes_chargebacks_manager.domain.models import (
    CaseHandle,
    ExtractedEvidence,
)
from disputes_chargebacks_manager.domain.workflows import CARD_SCHEME_WORKFLOW

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="open_dispute",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="DSP-1001 (FICTIONAL): ineligible rejection",
    citations=(Citation(source_id="pack:card", title="Reason-code pack", snippet="10.4"),),
)

#: The escalated disposition every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = sample_cases.CANONICAL_DISPOSITION

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _case_invoke(adapter: Any) -> Any:
    return adapter.open_case(
        sample_cases.CANONICAL_DISPUTE,
        CARD_SCHEME_WORKFLOW,
        opened_on=sample_cases.CANONICAL_DISPUTE.intake_date,
    )


def _case_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, CaseHandle) and bool(result.case_id) and bool(result.deadlines)


def _extract_invoke(adapter: Any) -> Any:
    return adapter.extract_raw(
        sample_cases.EVIDENCE_TEXT, doc_type="chargeback_evidence", document_id="EV-1"
    )


def _extract_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, ExtractedEvidence) and bool(result.fields)


def _channel_invoke(adapter: Any) -> Any:
    return adapter.fetch_turns("conv-unauth-001")


def _channel_answered(_adapter: Any, result: Any) -> bool:
    return bool(result)


def _regulator_invoke(adapter: Any) -> Any:
    return adapter.draft_response(
        dispute_id="DSP-1005", category="complaint", redacted_narrative="a complaint narrative"
    )


def _regulator_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "draft_text", "")) and result.requires_human_review


def _narration_invoke(adapter: Any) -> Any:
    return adapter.narrate(instruction="Summarise the case.", facts=(("reason_code", "10.4"),))


def _narration_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, str) and bool(result)


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated result to human review",
    ),
    "case_engine": PortCase(
        invoke=_case_invoke,
        answered=_case_answered,
        # With no case spine configured the managed engine refuses, not opens a case nowhere.
        managed_refusal=(RuntimeError,),
        detail="open a case with computed clocks",
    ),
    "document_extraction": PortCase(
        invoke=_extract_invoke,
        answered=_extract_answered,
        # The lazy `google.cloud` Document AI import is the first thing the managed extractor does.
        managed_refusal=(ImportError,),
        detail="extract cited fields from an evidence document",
    ),
    "conversation_channel": PortCase(
        invoke=_channel_invoke,
        answered=_channel_answered,
        # The lazy Dialogflow import is the first thing the managed channel does.
        managed_refusal=(ImportError,),
        detail="return the turns of an intake conversation",
    ),
    "regulator_response": PortCase(
        invoke=_regulator_invoke,
        answered=_regulator_answered,
        # With no Doc6 endpoint configured the managed adapter refuses, not returns a blank draft.
        managed_refusal=(RuntimeError,),
        detail="draft a review-gated regulator response",
    ),
    "narration": PortCase(
        invoke=_narration_invoke,
        answered=_narration_answered,
        # The lazy Vertex import is the first thing the managed narrator does.
        managed_refusal=(ImportError,),
        detail="narrate a paragraph over engine facts",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
