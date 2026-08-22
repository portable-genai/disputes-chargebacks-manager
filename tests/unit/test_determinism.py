"""Determinism: the consequential numbers and verdicts do not move when generation is stubbed.

The house invariant is that every consequential figure and disposition comes from PURE engine
code, and the model only narrates. The proof required is concrete: with the generation adapter
(the ``NarrationPort``) replaced by one that returns wrong-but-valid noise, the numeric output is
IDENTICAL. ``open_dispute`` and ``assess_abuse`` never touch the port at all, so a divergence
here would mean a number had leaked into the model's hands; there is none to leak.
"""

from __future__ import annotations

from typing import Any

from disputes_chargebacks_manager.config import build_container
from disputes_chargebacks_manager.domain.dispute_service import DisputeService

from tests.conftest import local_settings
from tests.fixtures import sample_cases


class _PoisonNarrator:
    """A generation adapter that answers, but with noise unrelated to any engine fact.

    If a consequential number depended on the model, swapping the real narrator for this one
    would change it. The classification returns a valid-but-arbitrary label and the narration a
    fixed string carrying a figure (``424242``) that appears in no case, so any dependency shows.
    """

    def classify(self, text: str, *, categories: tuple[str, ...]) -> str:
        return categories[-1]

    def narrate(self, *, instruction: str, facts: tuple[tuple[str, str], ...]) -> str:
        return "POISON 424242 unrelated narration"


def _service(narration: Any) -> DisputeService:
    """A dispute service on the real local stack, but with ``narration`` swapped in."""
    container = build_container(local_settings())
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


def _open_fingerprint(service: DisputeService, dispute: Any) -> tuple[Any, ...]:
    result = service.open_dispute(dispute, actor=sample_cases.ACTOR, as_of=sample_cases.AS_OF)
    return (
        result.eligibility.eligible,
        result.eligibility.response_deadline,
        tuple(result.eligibility.reasons),
        result.case.state.value,
        tuple((d.name, d.due, d.regulatory) for d in result.case.deadlines),
        result.disposition.severity.value,
        result.disposition.decision.value,
        result.disposition.requires_human_review,
    )


def _abuse_fingerprint(service: DisputeService, dispute: Any, history: Any) -> tuple[Any, ...]:
    decision = service.assess_abuse(dispute, history, actor=sample_cases.ACTOR)
    return (
        decision.assessment.outcome.value,
        decision.assessment.score,
        tuple(decision.assessment.signals),
        decision.disposition.severity.value if decision.disposition else None,
    )


def test_open_dispute_numbers_are_identical_under_stubbed_generation() -> None:
    real = _service(build_container(local_settings()).narration)
    stub = _service(_PoisonNarrator())
    for dispute in (sample_cases.ELIGIBLE_DISPUTE, sample_cases.INELIGIBLE_DISPUTE):
        assert _open_fingerprint(real, dispute) == _open_fingerprint(stub, dispute)


def test_abuse_numbers_are_identical_under_stubbed_generation() -> None:
    real = _service(build_container(local_settings()).narration)
    stub = _service(_PoisonNarrator())
    pairs = (
        (sample_cases.ABUSE_DISPUTE, sample_cases.ABUSIVE_HISTORY),
        (sample_cases.CLEAN_DISPUTE, sample_cases.CLEAN_HISTORY),
    )
    for dispute, history in pairs:
        assert _abuse_fingerprint(real, dispute, history) == _abuse_fingerprint(
            stub, dispute, history
        )


def test_the_stub_narrator_really_is_a_different_generation() -> None:
    """Guard the guard: if the poison narrator returned the same prose, the test proves nothing."""
    dispute = sample_cases.ELIGIBLE_DISPUTE
    evidence = (("EV-1", sample_cases.EVIDENCE_TEXT),)
    real_pack = _service(build_container(local_settings()).narration).draft_representment(
        dispute, evidence, actor=sample_cases.ACTOR
    )
    stub_pack = _service(_PoisonNarrator()).draft_representment(
        dispute, evidence, actor=sample_cases.ACTOR
    )
    # The narrated prose differs (the model was swapped)...
    assert real_pack.draft_text != stub_pack.draft_text
    # ...while the engine-fixed facts on the pack do not.
    assert real_pack.requires_human_review == stub_pack.requires_human_review is True
    assert real_pack.citations == stub_pack.citations
