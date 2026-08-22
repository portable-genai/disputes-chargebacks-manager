"""Deterministic reason-code eligibility, fail-closed on any unknown code.

Reason-code packs are DATA, not code (SPEC: F2 slice 3): per-scheme eligibility windows, evidence
requirements and deadlines loaded from ``config/policy_packs.yaml`` into the frozen structures
below and handed to this pure engine. The engine owns the verdict: an explicit ``as_of`` date, a
day-count comparison against the filing window, and a fail-closed default for a reason code the
pack does not name. No model produces any part of an :class:`EligibilityOutcome`.

Fail closed means: an unknown reason code is INELIGIBLE with a stated reason, never "assume
eligible". A dispute filed after its window is INELIGIBLE. Both outcomes are consequential inputs
to the lifecycle, so the reasoning is a deterministic, replayable list of citations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .kernel import Citation
from .models import Dispute, DisputeTrack, EligibilityOutcome


@dataclass(frozen=True, slots=True)
class ReasonCodeRule:
    """One reason code's policy: how long a filing window, what evidence, what response deadline."""

    code: str
    description: str
    filing_window_days: int
    response_deadline_days: int
    evidence_required: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReasonCodePack:
    """A per-track set of reason-code rules. The union across tracks is the shipped policy."""

    track: DisputeTrack
    scheme: str
    rules: tuple[ReasonCodeRule, ...]

    def rule_for(self, code: str) -> ReasonCodeRule | None:
        for rule in self.rules:
            if rule.code == code:
                return rule
        return None


class UnknownTrackError(KeyError):
    """Raised when no pack is registered for a dispute's track (fail closed, not a default pack)."""


class EligibilityEngine:
    """Assess a dispute against the reason-code pack for its track. Pure and replayable."""

    def __init__(self, packs: tuple[ReasonCodePack, ...]) -> None:
        # Index by track. A dispute whose track has no pack fails closed at assess time.
        self._by_track: dict[DisputeTrack, ReasonCodePack] = {p.track: p for p in packs}

    def pack_for(self, track: DisputeTrack) -> ReasonCodePack:
        try:
            return self._by_track[track]
        except KeyError as exc:
            raise UnknownTrackError(
                f"no reason-code pack registered for track {track.value!r}"
            ) from exc

    def assess(self, dispute: Dispute, *, as_of: date) -> EligibilityOutcome:
        """Return the eligibility verdict for ``dispute`` as of ``as_of``.

        Order of checks is deterministic and each appends a citation: unknown code first (fail
        closed), then the filing-window comparison. The response deadline is computed only when
        the dispute is otherwise eligible, so an ineligible outcome never advertises a deadline it
        will not honour.
        """
        pack = self.pack_for(dispute.track)
        rule = pack.rule_for(dispute.reason_code)
        reasons: list[str] = []
        citations: list[Citation] = []

        if rule is None:
            reasons.append(
                f"reason code {dispute.reason_code!r} is not in the {pack.scheme} pack; "
                "unknown codes are ineligible by policy (fail closed)"
            )
            citations.append(
                Citation(
                    source_id=f"pack:{pack.scheme}",
                    title="Reason-code pack",
                    snippet=f"no rule for {dispute.reason_code}",
                )
            )
            return EligibilityOutcome(
                dispute_id=dispute.id,
                reason_code=dispute.reason_code,
                eligible=False,
                reasons=tuple(reasons),
                as_of=as_of,
                citations=tuple(citations),
            )

        age_days = (dispute.intake_date - dispute.transaction_date).days
        within_window = 0 <= age_days <= rule.filing_window_days
        citations.append(
            Citation(
                source_id=f"pack:{pack.scheme}:{rule.code}",
                title=rule.description,
                snippet=(
                    f"filing window {rule.filing_window_days}d; "
                    f"filed at {age_days}d after transaction"
                ),
            )
        )
        if age_days < 0:
            reasons.append("intake date precedes the transaction date, which is impossible")
            eligible = False
        elif not within_window:
            reasons.append(
                f"filed {age_days}d after the transaction, past the "
                f"{rule.filing_window_days}d window for {rule.code}"
            )
            eligible = False
        else:
            reasons.append(f"within the {rule.filing_window_days}d window for {rule.code}")
            eligible = True

        deadline = (
            dispute.intake_date + timedelta(days=rule.response_deadline_days) if eligible else None
        )
        return EligibilityOutcome(
            dispute_id=dispute.id,
            reason_code=dispute.reason_code,
            eligible=eligible,
            reasons=tuple(reasons),
            as_of=as_of,
            response_deadline=deadline,
            citations=tuple(citations),
        )
