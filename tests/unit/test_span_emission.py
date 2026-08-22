"""Opening a dispute opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing the open path depends entirely on the span carrying structural
attributes only: which action, whose, which tenant, which track. A dispute id, a customer or
merchant reference or a narrative fragment reaching a span has left the boundary the service's
``redact`` call exists to hold, and it has left it silently.

The content case drives the dispute whose narrative carries a planted NRIC, so the check runs
against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from disputes_chargebacks_manager.config import build_container
from disputes_chargebacks_manager.domain.dispute_service import DisputeService, OpenDisputeResult
from disputes_chargebacks_manager.domain.models import Dispute

from tests.conftest import local_settings
from tests.fixtures import sample_cases

#: Every attribute key the open span is allowed to carry. A rejection that started explaining
#: itself on the span (a reason, a reference, a narrative) would widen this set, which is the
#: point of asserting on the set rather than on the individual keys.
_OPEN_KEYS = {"action", "actor", "tenant", "track"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _service(tracer: _RecordingTracer) -> DisputeService:
    """The REAL local adapters, exactly as ``config.build_service`` wires them."""
    container = build_container(local_settings())
    return DisputeService(
        audit=container.audit,
        review_router=container.review_router,
        case_engine=container.case_engine,
        narration=container.narration,
        document_extraction=container.document_extraction,
        conversation_channel=container.conversation_channel,
        regulator_response=container.regulator_response,
        tracer=tracer,  # type: ignore[arg-type]
        reason_code_packs=container.settings.reason_code_packs,
        abuse_policy=container.settings.abuse_policy,
    )


def _open(dispute: Dispute) -> tuple[_RecordingTracer, OpenDisputeResult]:
    tracer = _RecordingTracer()
    result = _service(tracer).open_dispute(
        dispute, actor=sample_cases.ACTOR, as_of=sample_cases.AS_OF
    )
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute VALUE that was emitted, and every KEY, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_opening_a_dispute_opens_exactly_one_named_span() -> None:
    tracer, _ = _open(sample_cases.ELIGIBLE_DISPUTE)
    assert [name for name, _ in tracer.spans] == ["disputes.open_dispute"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose open path is slow, on which tenant and track", nothing more."""
    tracer, _ = _open(sample_cases.ELIGIBLE_DISPUTE)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "open_dispute"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT
    assert attributes["track"] == sample_cases.ELIGIBLE_DISPUTE.track.value


@pytest.mark.parametrize(
    "dispute",
    [sample_cases.ELIGIBLE_DISPUTE, sample_cases.INELIGIBLE_DISPUTE, sample_cases.PII_DISPUTE],
    ids=["eligible", "ineligible", "pii"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(dispute: Dispute) -> None:
    """A machine rejection must not start attaching its reasons, or the case, to the span."""
    tracer, _ = _open(dispute)
    for _, attributes in tracer.spans:
        assert set(attributes) == _OPEN_KEYS


def test_no_span_attribute_carries_dispute_content_or_the_planted_identifier() -> None:
    """The dispute used here has an NRIC planted in its narrative, so a leak would show."""
    tracer, result = _open(sample_cases.PII_DISPUTE)
    emitted = _emitted(tracer)

    forbidden = [
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_DISPUTE.narrative,
        "ops@gamma.example",
        sample_cases.PII_DISPUTE.id,
        sample_cases.PII_DISPUTE.customer_ref,
        result.disposition.summary,
        result.disposition.outcome_label,
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _open(sample_cases.ELIGIBLE_DISPUTE)
    values: list[Any] = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
