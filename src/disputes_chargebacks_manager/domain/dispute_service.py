"""The dispute orchestrator: deterministic engines decide, the model only narrates, R8 routes.

Every consequential outcome here (ineligible rejection, an abuse DENY or REVIEW, a representment
draft, a regulator response) is produced by a pure engine and marked ``requires_human_review``;
the orchestrator redacts before the audit write and hands the disposition to the review router in
the SAME call that produced it (rule R8). The model's only jobs are behind the narration port:
classify an intake into the closed set, and narrate a draft over facts the engine already fixed.

The orchestrator takes its ports by constructor injection (the container supplies the bound
adapter family) and builds the deterministic engines from the settings-loaded policy, so a test
drives it with in-memory settings and the real local adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.case_engine import CaseEnginePort
from ..ports.conversation_channel import ConversationChannelPort
from ..ports.document_extraction import DocumentExtractionPort
from ..ports.narration import NarrationPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.regulator_response import RegulatorResponsePort
from ..ports.review_router import ReviewRouterPort
from .abuse_engine import AbuseEngine, AbusePolicy
from .eligibility_engine import EligibilityEngine, ReasonCodePack
from .kernel import AuditEvent, Citation, Decision, Severity, utcnow
from .models import (
    AbuseAssessment,
    AbuseOutcome,
    CaseHandle,
    CustomerHistory,
    Dispute,
    DisputeDisposition,
    DisputeState,
    EligibilityOutcome,
    ExtractedEvidence,
    IntakeCategory,
    IntakeClassification,
    RegulatorDraft,
    RepresentmentPack,
)
from .pii import PII_PATTERNS
from .workflows import workflow_for

_ABUSE_SEVERITY = {
    AbuseOutcome.DENY: Severity.CRITICAL,
    AbuseOutcome.REVIEW: Severity.HIGH,
    AbuseOutcome.ALLOW: Severity.LOW,
}

#: The closed set of intake labels the model may choose from (the enum's string values).
_INTAKE_CATEGORIES: tuple[str, ...] = tuple(
    c.value for c in IntakeCategory if c is not IntakeCategory.UNKNOWN
)

#: One span per opened dispute. Structural attributes only: see :meth:`DisputeService.open_dispute`.
_OPEN_DISPUTE_SPAN = "disputes.open_dispute"


def _redacted(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
    """Mask every citation SNIPPET, leaving the locator and the title alone.

    A snippet is a slice of its source, so an extractor-built one is a raw document line. An
    engine-built one quotes a policy rule and has nothing to mask, and no sink can tell the two
    apart by inspection, so the boundary masks unconditionally: redacting text that carries no
    identifier is a no-op, while deciding per caller is how one caller ends up forgetting.
    """
    return tuple(
        Citation(source_id=c.source_id, title=c.title, snippet=redact(c.snippet, PII_PATTERNS))
        for c in citations
    )


@dataclass(frozen=True, slots=True)
class OpenDisputeResult:
    """Opening a dispute: the eligibility verdict, the opened case, and the R8 disposition."""

    eligibility: EligibilityOutcome
    case: CaseHandle
    disposition: DisputeDisposition
    review_ref: str


@dataclass(frozen=True, slots=True)
class AbuseDecision:
    """A refund-abuse assessment plus its R8 disposition (populated when consequential)."""

    assessment: AbuseAssessment
    disposition: DisputeDisposition | None
    review_ref: str


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """An intake classification plus, when it fails closed, the review disposition."""

    classification: IntakeClassification
    opened: bool
    disposition: DisputeDisposition | None
    review_ref: str


class DisputeService:
    """Orchestrate the dispute lifecycle over deterministic engines and injected ports."""

    def __init__(
        self,
        *,
        audit: AuditSinkPort,
        review_router: ReviewRouterPort,
        case_engine: CaseEnginePort,
        narration: NarrationPort,
        document_extraction: DocumentExtractionPort,
        conversation_channel: ConversationChannelPort,
        regulator_response: RegulatorResponsePort,
        tracer: ObservabilityTracerPort,
        reason_code_packs: tuple[ReasonCodePack, ...],
        abuse_policy: AbusePolicy,
    ) -> None:
        self._audit = audit
        self._review = review_router
        self._case_engine = case_engine
        self._narration = narration
        self._extractor = document_extraction
        self._channel = conversation_channel
        self._regulator = regulator_response
        self._tracer = tracer
        self._eligibility = EligibilityEngine(reason_code_packs)
        self._abuse = AbuseEngine(abuse_policy)

    # -- helpers ---------------------------------------------------------- #
    def _record(
        self,
        action: str,
        actor: str,
        decision: Decision,
        severity: Severity,
        summary: str,
        citations: tuple[Citation, ...],
    ) -> None:
        self._audit.record(
            AuditEvent(
                action=action,
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=redact(summary, PII_PATTERNS),
                citations=_redacted(citations),
                timestamp=utcnow(),
            )
        )

    def _route(self, disposition: DisputeDisposition, *, maker: str, tenant: str) -> str:
        return self._review.route(disposition, maker=maker, tenant=tenant)

    # -- open / eligibility ---------------------------------------------- #
    def open_dispute(self, dispute: Dispute, *, actor: str, as_of: date) -> OpenDisputeResult:
        """Assess eligibility, open a case on the spine, and route an ineligible rejection.

        Eligibility is deterministic. An eligible dispute opens on ``EVIDENCE_REVIEW`` and is not
        itself consequential (no review). An INELIGIBLE dispute is a consequential rejection: it
        advances to ``REJECTED`` and routes to human review, because a machine-rejected customer
        dispute must be signed off.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        dispute id, the customer or merchant references or the narrative text: a trace backend
        is not the WORM audit trail. It has no redaction stage, a wider read audience and no
        retention rule written against a regulator's requirement, so anything content-shaped
        that reaches a span has left the boundary the ``redact`` call exists to hold, silently.
        """
        with self._tracer.span(
            _OPEN_DISPUTE_SPAN,
            action="open_dispute",
            actor=actor,
            tenant=dispute.tenant,
            track=dispute.track.value,
        ):
            workflow = workflow_for(dispute.track)
            eligibility = self._eligibility.assess(dispute, as_of=as_of)
            case = self._case_engine.open_case(dispute, workflow, opened_on=dispute.intake_date)

            if eligibility.eligible:
                case = self._case_engine.record_transition(
                    case, DisputeState.ELIGIBILITY_CHECK, trigger="submit"
                )
                case = self._case_engine.record_transition(
                    case, DisputeState.EVIDENCE_REVIEW, trigger="eligible"
                )
                decision, severity, needs_review = Decision.ALLOWED, Severity.MEDIUM, False
                label = "eligible: advanced to evidence review"
            else:
                case = self._case_engine.record_transition(
                    case, DisputeState.ELIGIBILITY_CHECK, trigger="submit"
                )
                case = self._case_engine.record_transition(
                    case, DisputeState.REJECTED, trigger="ineligible"
                )
                decision, severity, needs_review = Decision.ESCALATED, Severity.HIGH, True
                label = "ineligible: rejection requires human sign-off"

            summary = f"{dispute.id} ({dispute.track.value} {dispute.reason_code}): {label}"
            disposition = DisputeDisposition(
                subject=dispute.id,
                severity=severity,
                decision=decision,
                summary=summary,
                requires_human_review=needs_review,
                dispute_id=dispute.id,
                outcome_label=label,
                citations=eligibility.citations,
            )
            self._record("open_dispute", actor, decision, severity, summary, eligibility.citations)
            review_ref = (
                self._route(disposition, maker=actor, tenant=dispute.tenant) if needs_review else ""
            )
            return OpenDisputeResult(eligibility, case, disposition, review_ref)

    # -- refund abuse ----------------------------------------------------- #
    def assess_abuse(
        self, dispute: Dispute, history: CustomerHistory, *, actor: str
    ) -> AbuseDecision:
        """Score refund abuse; DENY and REVIEW are consequential and route to human sign-off."""
        assessment = self._abuse.assess(dispute, history)
        consequential = assessment.outcome in (AbuseOutcome.DENY, AbuseOutcome.REVIEW)
        severity = _ABUSE_SEVERITY[assessment.outcome]
        decision = Decision.ESCALATED if consequential else Decision.ALLOWED
        label = f"refund-abuse {assessment.outcome.value} (score {assessment.score})"
        summary = f"{dispute.id}: {label}; signals {', '.join(assessment.signals)}"
        self._record("assess_abuse", actor, decision, severity, summary, assessment.citations)

        if not consequential:
            return AbuseDecision(assessment, None, "")
        disposition = DisputeDisposition(
            subject=dispute.id,
            severity=severity,
            decision=decision,
            summary=summary,
            requires_human_review=True,
            dispute_id=dispute.id,
            outcome_label=label,
            citations=assessment.citations,
        )
        review_ref = self._route(disposition, maker=actor, tenant=dispute.tenant)
        return AbuseDecision(assessment, disposition, review_ref)

    # -- intake ----------------------------------------------------------- #
    def intake(self, conversation_ref: str, *, tenant: str, actor: str) -> IntakeResult:
        """Classify an intake conversation into the closed set; fail closed to review otherwise.

        The model classifies in-channel into :data:`_INTAKE_CATEGORIES` only. An UNKNOWN or
        out-of-set label never opens a lifecycle case: it routes to human review. A regulatory
        complaint also routes to review (it is handled by the regulator-response module, not a
        card/retail lifecycle). Only a clean card/retail category "opens" (is eligible to open).
        """
        turns = self._channel.fetch_turns(conversation_ref)
        transcript = " ".join(t.text for t in turns)
        raw_label = self._narration.classify(
            redact(transcript, PII_PATTERNS), categories=_INTAKE_CATEGORIES
        )
        category = (
            IntakeCategory(raw_label) if raw_label in _INTAKE_CATEGORIES else IntakeCategory.UNKNOWN
        )
        citation = Citation(
            source_id=f"intake:{conversation_ref}",
            title="Intake transcript",
            snippet=redact(transcript[:80], PII_PATTERNS),
        )

        opens = category not in (IntakeCategory.UNKNOWN, IntakeCategory.COMPLAINT_REGULATORY)
        if opens:
            reasons = (f"classified as {category.value}; eligible to open a lifecycle case",)
            classification = IntakeClassification(
                conversation_ref, category, True, reasons, (citation,)
            )
            self._record("intake", actor, Decision.ALLOWED, Severity.LOW, transcript, (citation,))
            return IntakeResult(classification, True, None, "")

        reason = (
            "regulatory complaint: routed to the regulator-response module and human review"
            if category is IntakeCategory.COMPLAINT_REGULATORY
            else "unclassifiable intake: fails closed to human review, no lifecycle case opened"
        )
        classification = IntakeClassification(
            conversation_ref, category, False, (reason,), (citation,)
        )
        summary = f"intake {conversation_ref}: {reason}"
        self._record("intake", actor, Decision.ESCALATED, Severity.MEDIUM, summary, (citation,))
        disposition = DisputeDisposition(
            subject=conversation_ref,
            severity=Severity.MEDIUM,
            decision=Decision.ESCALATED,
            summary=summary,
            requires_human_review=True,
            dispute_id=conversation_ref,
            outcome_label=reason,
            citations=(citation,),
        )
        review_ref = self._route(disposition, maker=actor, tenant=tenant)
        return IntakeResult(classification, False, disposition, review_ref)

    # -- representment ---------------------------------------------------- #
    def draft_representment(
        self, dispute: Dispute, evidence: tuple[tuple[str, str], ...], *, actor: str
    ) -> RepresentmentPack:
        """Parse evidence at the edge, then narrate a representment draft over engine facts only.

        ``evidence`` is a tuple of ``(document_id, raw_text)``. The extractor lifts fields at the
        edge; the narration port drafts prose from those fields and the dispute facts, never
        adding a figure absent from them. The pack always requires human review and never posts.

        The extractor's output is RAW customer document text (a field value verbatim, a snippet
        cut from the source line), and it reaches three sinks: the model, the WORM record and the
        pack the review console renders. So it is redacted HERE, as it crosses out of the edge,
        exactly as :meth:`regulator_response` redacts the narrative before delegating. Doing it
        at the sinks instead would mean getting it right three times.
        """
        extracted: list[ExtractedEvidence] = []
        facts: list[tuple[str, str]] = [
            ("dispute_id", dispute.id),
            ("reason_code", dispute.reason_code),
            ("amount_minor", str(dispute.amount_minor)),
            ("currency", dispute.currency),
        ]
        citations: list[Citation] = []
        for document_id, raw_text in evidence:
            doc = self._extractor.extract_raw(
                raw_text, doc_type="chargeback_evidence", document_id=document_id
            )
            extracted.append(doc)
            citations.extend(_redacted(doc.citations))
            facts.extend((key, redact(value, PII_PATTERNS)) for key, value in doc.fields)

        draft_body = self._narration.narrate(
            instruction=(
                "[DRAFT representment, requires review] Contest the chargeback for the merchant, "
                "citing only the recorded evidence."
            ),
            facts=tuple(facts),
        )
        summary = f"{dispute.id}: representment draft over {len(extracted)} evidence document(s)"
        self._record(
            "draft_representment",
            actor,
            Decision.ESCALATED,
            Severity.HIGH,
            summary,
            tuple(citations),
        )
        return RepresentmentPack(
            dispute_id=dispute.id,
            draft_text=draft_body,
            requires_human_review=True,
            citations=tuple(citations),
        )

    # -- regulator response (complaints-review) --------------------------------------- #
    def regulator_response(self, dispute: Dispute, *, actor: str) -> RegulatorDraft:
        """Delegate regulator-response drafting to the complaints-review module with a redacted
        narrative.
        """
        redacted = redact(dispute.narrative, PII_PATTERNS)
        draft = self._regulator.draft_response(
            dispute_id=dispute.id,
            category=dispute.reason_code or "complaint",
            redacted_narrative=redacted,
        )
        summary = f"{dispute.id}: regulator-response draft via complaints-review module"
        self._record(
            "regulator_response", actor, Decision.ESCALATED, Severity.HIGH, summary, draft.citations
        )
        return draft
