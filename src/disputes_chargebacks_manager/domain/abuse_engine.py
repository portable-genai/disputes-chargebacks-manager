"""Deterministic refund-abuse decisioning: velocity, history and threshold rules.

Pure stdlib. The verdict (ALLOW / REVIEW / DENY) is a deterministic function of a
:class:`~.models.CustomerHistory` and the dispute amount against a frozen
:class:`AbusePolicy`, whose numbers are the client's and live in ``config/policy_packs.yaml``.
A DENY or a REVIEW is CONSEQUENTIAL: the orchestrator sets ``requires_human_review`` and routes
it through the review kit (R8) with the severity mapped to Hrz7's maker-checker approval count.
The engine never auto-closes; it recommends, and a human confirms.

The score is a transparent sum of weighted signals so a reviewer can reconstruct it, and each
firing signal carries a citation naming the datum that fired it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kernel import Citation
from .models import AbuseAssessment, AbuseOutcome, CustomerHistory, Dispute


@dataclass(frozen=True, slots=True)
class AbusePolicy:
    """The bank-owned thresholds. Two review/deny bands over a transparent additive score."""

    #: Disputes in the trailing 90 days above which velocity is a firing signal.
    velocity_count_90d: int = 4
    #: A single dispute amount (minor units) above which the amount is a firing signal.
    high_amount_minor: int = 50_000
    #: Trailing-90-day refunded total (minor units) above which cumulative refunds fire.
    high_refund_total_minor: int = 200_000
    #: Points contributed by each signal.
    velocity_points: int = 2
    amount_points: int = 1
    refund_total_points: int = 2
    prior_abuse_points: int = 3
    #: Score at or above which the verdict is REVIEW, and (higher) DENY.
    review_at: int = 3
    deny_at: int = 5


class AbuseEngine:
    """Score a dispute for refund abuse and return a deterministic, cited verdict."""

    def __init__(self, policy: AbusePolicy) -> None:
        self._policy = policy

    def assess(self, dispute: Dispute, history: CustomerHistory) -> AbuseAssessment:
        p = self._policy
        score = 0
        signals: list[str] = []
        citations: list[Citation] = []

        def fire(name: str, points: int, source: str, snippet: str) -> None:
            nonlocal score
            score += points
            signals.append(f"{name} (+{points})")
            citations.append(Citation(source_id=source, title=name, snippet=snippet))

        if history.dispute_count_90d > p.velocity_count_90d:
            fire(
                "velocity",
                p.velocity_points,
                "history:velocity",
                f"{history.dispute_count_90d} disputes in 90d > {p.velocity_count_90d}",
            )
        if dispute.amount_minor > p.high_amount_minor:
            fire(
                "high_amount",
                p.amount_points,
                "dispute:amount",
                f"{dispute.amount_minor} {dispute.currency} minor > {p.high_amount_minor}",
            )
        if history.refund_total_minor_90d > p.high_refund_total_minor:
            fire(
                "cumulative_refunds",
                p.refund_total_points,
                "history:refunds",
                f"{history.refund_total_minor_90d} minor refunded in 90d > "
                f"{p.high_refund_total_minor}",
            )
        if history.prior_abuse_count > 0:
            fire(
                "prior_abuse",
                p.prior_abuse_points,
                "history:prior_abuse",
                f"{history.prior_abuse_count} prior confirmed-abuse case(s)",
            )

        if score >= p.deny_at:
            outcome = AbuseOutcome.DENY
        elif score >= p.review_at:
            outcome = AbuseOutcome.REVIEW
        else:
            outcome = AbuseOutcome.ALLOW
            if not signals:
                signals.append("no abuse signals fired")
                citations.append(
                    Citation(
                        source_id="history:clean",
                        title="No abuse signals",
                        snippet="velocity, amount, refunds and prior abuse all under threshold",
                    )
                )

        return AbuseAssessment(
            dispute_id=dispute.id,
            outcome=outcome,
            score=score,
            signals=tuple(signals),
            citations=tuple(citations),
        )
