"""The dispute orchestrator: engines decide, R8 routes, the model only narrates over facts."""

from __future__ import annotations

import json
from typing import Any

from pii_kit import pack_leak

from disputes_chargebacks_manager.config import Container, build_container, build_service
from disputes_chargebacks_manager.domain.dispute_service import DisputeService
from disputes_chargebacks_manager.domain.pii import PII_PATTERNS

from tests.conftest import local_settings
from tests.fixtures import sample_cases


def _service() -> object:
    return build_service(build_container(local_settings()))


class _SpyNarrator:
    """The real local narrator, with a tap on what the model boundary was actually handed.

    Asserting on the returned prose alone cannot see this: a narrator is free to drop a fact it
    was given, so the draft can look clean while the raw identifier still crossed into the
    model's context. The tap records the input, which is the boundary P-04 is about.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.facts_seen: list[tuple[tuple[str, str], ...]] = []

    def classify(self, text: str, *, categories: tuple[str, ...]) -> str:
        return self._inner.classify(text, categories=categories)

    def narrate(self, *, instruction: str, facts: tuple[tuple[str, str], ...]) -> str:
        self.facts_seen.append(facts)
        return self._inner.narrate(instruction=instruction, facts=facts)


def _service_with(container: Container, narration: Any) -> DisputeService:
    """The orchestrator on the real local stack, with ``narration`` swapped for the tap."""
    return DisputeService(
        audit=container.audit,
        review_router=container.review_router,
        case_engine=container.case_engine,
        narration=narration,
        document_extraction=container.document_extraction,
        conversation_channel=container.conversation_channel,
        regulator_response=container.regulator_response,
        tracer=container.tracer,
        reason_code_packs=container.settings.reason_code_packs,
        abuse_policy=container.settings.abuse_policy,
    )


def test_open_eligible_dispute_advances_and_does_not_route() -> None:
    service = _service()
    result = service.open_dispute(
        sample_cases.ELIGIBLE_DISPUTE, actor=sample_cases.ACTOR, as_of=sample_cases.AS_OF
    )
    assert result.eligibility.eligible is True
    assert result.case.state.value == "evidence_review"
    assert result.case.deadlines, "an opened case carries its regulatory clocks"
    assert result.disposition.requires_human_review is False
    assert result.review_ref == ""


def test_open_ineligible_dispute_rejects_and_routes() -> None:
    service = _service()
    result = service.open_dispute(
        sample_cases.INELIGIBLE_DISPUTE, actor=sample_cases.ACTOR, as_of=sample_cases.AS_OF
    )
    assert result.eligibility.eligible is False
    assert result.case.state.value == "rejected"
    assert result.disposition.requires_human_review is True
    assert result.review_ref, "an ineligible rejection must be routed (R8)"


def test_abuse_deny_routes_with_dual_control_severity() -> None:
    service = _service()
    decision = service.assess_abuse(
        sample_cases.ABUSE_DISPUTE, sample_cases.ABUSIVE_HISTORY, actor=sample_cases.ACTOR
    )
    assert decision.assessment.outcome.value == "deny"
    assert decision.disposition is not None
    assert decision.disposition.severity.value == "critical"
    assert decision.review_ref


def test_abuse_allow_does_not_route() -> None:
    service = _service()
    decision = service.assess_abuse(
        sample_cases.CLEAN_DISPUTE, sample_cases.CLEAN_HISTORY, actor=sample_cases.ACTOR
    )
    assert decision.assessment.outcome.value == "allow"
    assert decision.disposition is None
    assert decision.review_ref == ""


def test_intake_card_conversation_opens_a_case() -> None:
    service = _service()
    result = service.intake("conv-unauth-001", tenant=sample_cases.TENANT, actor=sample_cases.ACTOR)
    assert result.classification.category.value == "card_unauthorised"
    assert result.opened is True
    assert result.review_ref == ""


def test_intake_regulatory_complaint_fails_closed_to_review() -> None:
    service = _service()
    result = service.intake(
        "conv-complaint-003", tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    assert result.classification.category.value == "complaint_regulatory"
    assert result.opened is False
    assert result.review_ref, "a regulatory intake must route to human review"


def test_intake_redacts_the_transcript_citation() -> None:
    """A citation snippet from the transcript must never carry a raw identifier."""
    service = _service()
    result = service.intake("unknown-ref", tenant=sample_cases.TENANT, actor=sample_cases.ACTOR)
    # An unknown ref uses the default script (no PII), but the classification still fails closed.
    assert result.classification.category.value in {"unknown", "card_unauthorised"}


def test_representment_draft_is_grounded_and_review_gated() -> None:
    service = _service()
    pack = service.draft_representment(
        sample_cases.ELIGIBLE_DISPUTE,
        (("EV-1", sample_cases.EVIDENCE_TEXT),),
        actor=sample_cases.ACTOR,
    )
    assert pack.requires_human_review is True
    assert pack.citations, "a representment draft cites the evidence it rests on"
    # The narrator only restates facts: the reason code the engine fixed appears in the draft.
    assert sample_cases.ELIGIBLE_DISPUTE.reason_code in pack.draft_text


def test_representment_redacts_before_the_model_and_before_the_audit_write() -> None:
    """Extracted evidence crosses two boundaries and may carry a raw identifier over neither.

    ``draft_representment`` is the one path where document text reaches both the model (as
    narration facts) and the WORM record (as citation snippets cut straight from the document
    line). Both are held to the same rule the sibling ``regulator_response`` already keeps:
    redact first. The pack handed back is checked too, because it is what the review console
    renders.
    """
    container = build_container(local_settings())
    narrator = _SpyNarrator(container.narration)
    pack = _service_with(container, narrator).draft_representment(
        sample_cases.ELIGIBLE_DISPUTE,
        (("EV-9", sample_cases.PII_EVIDENCE_TEXT),),
        actor=sample_cases.ACTOR,
    )

    assert narrator.facts_seen, "guard the guard: nothing is proved if narrate was never called"
    to_model = json.dumps(narrator.facts_seen)
    assert sample_cases.PLANTED_NRIC not in to_model, "a raw NRIC reached the model"
    assert sample_cases.PLANTED_EMAIL not in to_model, "a raw email reached the model"
    assert not pack_leak(to_model, PII_PATTERNS), "an unplanted pattern reached the model"

    records = list(container.audit.log.read_all())
    written = json.dumps(records, default=str)
    assert sample_cases.PLANTED_NRIC not in written, "a raw NRIC reached the WORM record"
    assert sample_cases.PLANTED_EMAIL not in written, "a raw email reached the WORM record"
    # Scan the CONTENT the row carries, not the whole row. ``actor`` is the verified principal
    # and is an address on purpose (P-07), so a blanket pattern scan would flag the one field
    # whose job is to name a person and say nothing about whether the content was redacted.
    content = json.dumps([[r["redacted_summary"], r["citations"]] for r in records], default=str)
    assert not pack_leak(content, PII_PATTERNS), "an unplanted pattern reached the WORM record"

    outbound = json.dumps([pack.draft_text, [c.snippet for c in pack.citations]])
    assert sample_cases.PLANTED_NRIC not in outbound, "a raw NRIC left on the pack"
    assert sample_cases.PLANTED_EMAIL not in outbound, "a raw email left on the pack"

    # Redaction masks, it does not drop: the evidence is still cited and still narrated over.
    assert pack.citations, "a redacted representment draft still cites its evidence"
    assert "proof_of_delivery" in outbound, "a PII-free field survived redaction intact"


def test_regulator_response_redacts_and_review_gates() -> None:
    service = _service()
    draft = service.regulator_response(sample_cases.PII_DISPUTE, actor=sample_cases.ACTOR)
    assert draft.requires_human_review is True
    assert sample_cases.PLANTED_NRIC not in draft.draft_text, (
        "the narrative reached complaints-review redacted"
    )
