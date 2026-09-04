"""Vertical artifact models: the disputes-and-chargebacks request and result types.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py`` (``Citation``, ``AuditEvent``, ``Severity``, ``Decision``). A fork building a
different vertical rewrites this module and keeps ``kernel.py`` untouched.

Every consequential number and outcome on these types is produced by a deterministic engine
(``eligibility_engine``, ``abuse_engine``, ``state_machine``), never by a model. The model may
narrate a :class:`DisputeDisposition` summary, but it may never set the severity, the eligibility
verdict or the abuse outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class DisputeTrack(LenientStrEnum):
    """Which lifecycle a dispute runs: card-scheme (banking) or buyer-dispute (retail)."""

    CARD_SCHEME = "card_scheme"
    RETAIL = "retail"


class DisputeState(LenientStrEnum):
    """The states of a dispute lifecycle. Legality of moves lives in ``state_machine``."""

    INTAKE = "intake"
    ELIGIBILITY_CHECK = "eligibility_check"
    EVIDENCE_REVIEW = "evidence_review"
    REPRESENTMENT = "representment"
    PRE_ARBITRATION = "pre_arbitration"
    ARBITRATION = "arbitration"
    REFUND_ISSUED = "refund_issued"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    CLOSED_ABUSE = "closed_abuse"
    REJECTED = "rejected"


class IntakeCategory(LenientStrEnum):
    """The CLOSED set an in-channel intake may be classified into. Anything else is UNKNOWN.

    The model may only choose from this set; a value outside it is a fail-closed to human review,
    never an open-ended free-text label reaching the deterministic path.
    """

    CARD_UNAUTHORISED = "card_unauthorised"
    CARD_GOODS_NOT_RECEIVED = "card_goods_not_received"
    CARD_NOT_AS_DESCRIBED = "card_not_as_described"
    RETAIL_REFUND = "retail_refund"
    RETAIL_NOT_RECEIVED = "retail_not_received"
    COMPLAINT_REGULATORY = "complaint_regulatory"
    UNKNOWN = "unknown"


class AbuseOutcome(LenientStrEnum):
    """The refund-abuse engine's verdict. DENY and REVIEW are consequential (route to R8)."""

    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Dispute:
    """One dispute or chargeback under management. Amounts are integer MINOR units (cents)."""

    id: str
    tenant: str
    track: DisputeTrack
    reason_code: str
    amount_minor: int
    currency: str
    transaction_date: date
    intake_date: date
    product: str = ""
    market: str = ""
    channel: str = ""
    customer_ref: str = ""
    merchant_ref: str = ""
    narrative: str = ""


@dataclass(frozen=True, slots=True)
class CaseDeadline:
    """One computed deadline on an open case, from a workflow ``ClockSpec``."""

    name: str
    due: date
    regulatory: bool


@dataclass(frozen=True, slots=True)
class CaseHandle:
    """The case-engine's receipt for an opened or advanced case (human-review-console spine or local
    recorder).
    """

    case_id: str
    dispute_id: str
    state: DisputeState
    deadlines: tuple[CaseDeadline, ...]

    def earliest_deadline(self) -> CaseDeadline | None:
        return min(self.deadlines, key=lambda d: d.due) if self.deadlines else None


@dataclass(frozen=True, slots=True)
class EligibilityOutcome:
    """The deterministic eligibility verdict for a dispute against its reason-code pack."""

    dispute_id: str
    reason_code: str
    eligible: bool
    reasons: tuple[str, ...]
    as_of: date
    response_deadline: date | None = None
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class CustomerHistory:
    """The prior-behaviour signals the abuse engine reads. Deterministic inputs, no model."""

    dispute_count_90d: int = 0
    prior_abuse_count: int = 0
    refund_total_minor_90d: int = 0


@dataclass(frozen=True, slots=True)
class AbuseAssessment:
    """The deterministic refund-abuse verdict, a score and the signals that produced it."""

    dispute_id: str
    outcome: AbuseOutcome
    score: int
    signals: tuple[str, ...]
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class IntakeTurn:
    """One turn of an intake conversation, from the channel port."""

    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class IntakeClassification:
    """The closed-set classification of an intake conversation, with eligibility outcome."""

    conversation_ref: str
    category: IntakeCategory
    eligible: bool
    reasons: tuple[str, ...]
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractedEvidence:
    """Fields lifted from a chargeback-evidence document at the edge (Document AI or stdlib)."""

    document_id: str
    doc_type: str
    fields: tuple[tuple[str, str], ...]
    citations: tuple[Citation, ...] = ()

    def field_map(self) -> dict[str, str]:
        return dict(self.fields)


@dataclass(frozen=True, slots=True)
class RepresentmentPack:
    """The drafted representment pack: model-narrated over engine facts, always review-gated."""

    dispute_id: str
    draft_text: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class RegulatorDraft:
    """A regulator-response draft produced by the complaints-review module, always review-gated."""

    dispute_id: str
    draft_text: str
    category: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class DisputeDisposition:
    """The R8 envelope: a consequential disposition routed to human review (maker-checker).

    Vertical-neutral in shape (subject, severity, decision, summary, review flag, citations) so
    the shared ``ReviewRouterPort`` and the ``review-kit`` payload converter carry it
    unchanged, plus the dispute id and a human-readable outcome label for the console.
    """

    subject: str
    severity: Severity
    decision: Decision
    summary: str
    requires_human_review: bool
    dispute_id: str = ""
    outcome_label: str = ""
    citations: tuple[Citation, ...] = field(default_factory=tuple)
