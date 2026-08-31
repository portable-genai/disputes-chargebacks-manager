"""API request/response schemas (Pydantic) mapped to and from the pure-domain models.

The schemas are the transport edge only: they validate shape and carry no policy. Every
consequential field on a response (eligibility, abuse outcome, severity, the review reference) is
copied from a domain result an engine produced, never computed here. The client NEVER asserts the
tenant or the actor: both come from the verified principal in ``api/app.py``.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.dispute_service import AbuseDecision as _AbuseDecisionResult
from ..domain.kernel import parse_date
from ..domain.models import (
    CustomerHistory,
    Dispute,
    DisputeTrack,
    RegulatorDraft,
    RepresentmentPack,
)


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


def _citations(items: object) -> list[CitationModel]:
    return [
        CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
        for c in items  # type: ignore[attr-defined]
    ]


class DisputeIn(BaseModel):
    """The dispute payload shared by every endpoint. Tenant is taken from the principal."""

    id: str
    track: str
    reason_code: str
    amount_minor: int
    currency: str
    transaction_date: str
    intake_date: str
    product: str = ""
    market: str = ""
    channel: str = ""
    customer_ref: str = ""
    merchant_ref: str = ""
    narrative: str = ""

    def to_domain(self, *, tenant: str) -> Dispute:
        return Dispute(
            id=self.id,
            tenant=tenant,
            track=DisputeTrack(self.track),
            reason_code=self.reason_code,
            amount_minor=self.amount_minor,
            currency=self.currency,
            transaction_date=parse_date(self.transaction_date),
            intake_date=parse_date(self.intake_date),
            product=self.product,
            market=self.market,
            channel=self.channel,
            customer_ref=self.customer_ref,
            merchant_ref=self.merchant_ref,
            narrative=self.narrative,
        )


class DeadlineModel(BaseModel):
    name: str
    due: str
    regulatory: bool


class OpenDisputeRequest(BaseModel):
    dispute: DisputeIn
    as_of: str


class OpenDisputeResponse(BaseModel):
    dispute_id: str
    eligible: bool
    reasons: list[str]
    state: str
    severity: str
    decision: str
    deadlines: list[DeadlineModel]
    requires_human_review: bool
    review_ref: str = ""
    citations: list[CitationModel] = []


class HistoryIn(BaseModel):
    dispute_count_90d: int = 0
    prior_abuse_count: int = 0
    refund_total_minor_90d: int = 0

    def to_domain(self) -> CustomerHistory:
        return CustomerHistory(
            dispute_count_90d=self.dispute_count_90d,
            prior_abuse_count=self.prior_abuse_count,
            refund_total_minor_90d=self.refund_total_minor_90d,
        )


class AbuseRequest(BaseModel):
    dispute: DisputeIn
    history: HistoryIn = HistoryIn()


class AbuseResponse(BaseModel):
    dispute_id: str
    outcome: str
    score: int
    signals: list[str]
    requires_human_review: bool
    review_ref: str = ""
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, decision: _AbuseDecisionResult, *, review_ref: str) -> AbuseResponse:
        a = decision.assessment
        return cls(
            dispute_id=a.dispute_id,
            outcome=a.outcome.value,
            score=a.score,
            signals=list(a.signals),
            requires_human_review=decision.disposition is not None,
            review_ref=review_ref,
            citations=_citations(a.citations),
        )


class IntakeRequest(BaseModel):
    conversation_ref: str


class IntakeResponse(BaseModel):
    conversation_ref: str
    category: str
    eligible: bool
    opened: bool
    reasons: list[str]
    requires_human_review: bool
    review_ref: str = ""
    citations: list[CitationModel] = []


class EvidenceIn(BaseModel):
    document_id: str
    text: str


class RepresentmentRequest(BaseModel):
    dispute: DisputeIn
    evidence: list[EvidenceIn] = []


class RepresentmentResponse(BaseModel):
    dispute_id: str
    draft_text: str
    requires_human_review: bool
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, pack: RepresentmentPack) -> RepresentmentResponse:
        return cls(
            dispute_id=pack.dispute_id,
            draft_text=pack.draft_text,
            requires_human_review=pack.requires_human_review,
            citations=_citations(pack.citations),
        )


class RegulatorRequest(BaseModel):
    dispute: DisputeIn


class RegulatorResponseModel(BaseModel):
    dispute_id: str
    draft_text: str
    category: str
    requires_human_review: bool
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, draft: RegulatorDraft) -> RegulatorResponseModel:
        return cls(
            dispute_id=draft.dispute_id,
            draft_text=draft.draft_text,
            category=draft.category,
            requires_human_review=draft.requires_human_review,
            citations=_citations(draft.citations),
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Both are read off the service because the browser cannot know either.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
