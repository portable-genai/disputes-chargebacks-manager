"""Dispute lifecycles as Hrz7 case-engine configuration: states, legal moves and clocks.

These are the ``WorkflowDefinition``s the Hrz7 case engine takes as per-vertical deployment
configuration (SPEC: F2 slice 2). They are DATA, not code paths: the deterministic
:mod:`.state_machine` reads them, and the ``case_engine`` port hands them to Hrz7 (platform
adapter) or computes deadlines from the same ``ClockSpec`` data (local recording adapter). The
LLM owns nothing here; transition legality, clocks and escalation are wholly deterministic.

Two tracks ship: card-scheme (banking chargebacks, with representment / pre-arbitration /
arbitration) and retail buyer-dispute (refund-oriented, shorter). A deployment adds a third by
appending a definition and registering it, never by editing the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import DisputeState, DisputeTrack


@dataclass(frozen=True, slots=True)
class ClockSpec:
    """One regulatory or operational clock: a named deadline measured in whole days from open.

    ``regulatory`` marks a clock whose breach carries a compliance consequence (a scheme-response
    or statutory refund window) as opposed to a purely operational SLA, so the ranking and the
    R8 severity mapping can treat the two differently.
    """

    name: str
    days: int
    regulatory: bool = False


@dataclass(frozen=True, slots=True)
class Transition:
    """One legal move: from ``source`` to ``target`` on ``trigger``."""

    source: DisputeState
    target: DisputeState
    trigger: str


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """A whole dispute lifecycle: its states, legal transitions, clocks and terminal states."""

    track: DisputeTrack
    initial: DisputeState
    states: tuple[DisputeState, ...]
    transitions: tuple[Transition, ...]
    clocks: tuple[ClockSpec, ...]
    terminal: tuple[DisputeState, ...]

    def legal_targets(self, source: DisputeState) -> tuple[DisputeState, ...]:
        """Every state reachable from ``source`` in one legal move, in declared order."""
        return tuple(t.target for t in self.transitions if t.source == source)

    def trigger_for(self, source: DisputeState, target: DisputeState) -> str | None:
        for t in self.transitions:
            if t.source == source and t.target == target:
                return t.trigger
        return None

    def is_terminal(self, state: DisputeState) -> bool:
        return state in self.terminal


_S = DisputeState

CARD_SCHEME_WORKFLOW = WorkflowDefinition(
    track=DisputeTrack.CARD_SCHEME,
    initial=_S.INTAKE,
    states=(
        _S.INTAKE,
        _S.ELIGIBILITY_CHECK,
        _S.EVIDENCE_REVIEW,
        _S.REPRESENTMENT,
        _S.PRE_ARBITRATION,
        _S.ARBITRATION,
        _S.REFUND_ISSUED,
        _S.CLOSED_WON,
        _S.CLOSED_LOST,
        _S.CLOSED_ABUSE,
        _S.REJECTED,
    ),
    transitions=(
        Transition(_S.INTAKE, _S.ELIGIBILITY_CHECK, "submit"),
        Transition(_S.ELIGIBILITY_CHECK, _S.EVIDENCE_REVIEW, "eligible"),
        Transition(_S.ELIGIBILITY_CHECK, _S.REJECTED, "ineligible"),
        Transition(_S.EVIDENCE_REVIEW, _S.REPRESENTMENT, "contest"),
        Transition(_S.EVIDENCE_REVIEW, _S.REFUND_ISSUED, "accept_liability"),
        Transition(_S.EVIDENCE_REVIEW, _S.CLOSED_ABUSE, "abuse_confirmed"),
        Transition(_S.REPRESENTMENT, _S.PRE_ARBITRATION, "issuer_reasserts"),
        Transition(_S.REPRESENTMENT, _S.CLOSED_WON, "represented"),
        Transition(_S.PRE_ARBITRATION, _S.ARBITRATION, "escalate"),
        Transition(_S.PRE_ARBITRATION, _S.CLOSED_WON, "withdrawn"),
        Transition(_S.ARBITRATION, _S.CLOSED_WON, "ruling_for_merchant"),
        Transition(_S.ARBITRATION, _S.CLOSED_LOST, "ruling_for_issuer"),
        Transition(_S.REFUND_ISSUED, _S.CLOSED_LOST, "close"),
    ),
    clocks=(
        ClockSpec("scheme_response", days=20, regulatory=True),
        ClockSpec("evidence_gather", days=7),
        ClockSpec("pre_arbitration_response", days=30, regulatory=True),
    ),
    terminal=(_S.CLOSED_WON, _S.CLOSED_LOST, _S.CLOSED_ABUSE, _S.REJECTED),
)

RETAIL_WORKFLOW = WorkflowDefinition(
    track=DisputeTrack.RETAIL,
    initial=_S.INTAKE,
    states=(
        _S.INTAKE,
        _S.ELIGIBILITY_CHECK,
        _S.EVIDENCE_REVIEW,
        _S.REFUND_ISSUED,
        _S.CLOSED_WON,
        _S.CLOSED_LOST,
        _S.CLOSED_ABUSE,
        _S.REJECTED,
    ),
    transitions=(
        Transition(_S.INTAKE, _S.ELIGIBILITY_CHECK, "submit"),
        Transition(_S.ELIGIBILITY_CHECK, _S.EVIDENCE_REVIEW, "eligible"),
        Transition(_S.ELIGIBILITY_CHECK, _S.REJECTED, "ineligible"),
        Transition(_S.EVIDENCE_REVIEW, _S.REFUND_ISSUED, "refund_approved"),
        Transition(_S.EVIDENCE_REVIEW, _S.CLOSED_WON, "seller_upheld"),
        Transition(_S.EVIDENCE_REVIEW, _S.CLOSED_ABUSE, "abuse_confirmed"),
        Transition(_S.REFUND_ISSUED, _S.CLOSED_LOST, "close"),
    ),
    clocks=(
        ClockSpec("seller_response", days=3),
        ClockSpec("refund_window", days=14, regulatory=True),
    ),
    terminal=(_S.CLOSED_WON, _S.CLOSED_LOST, _S.CLOSED_ABUSE, _S.REJECTED),
)

#: The per-vertical workflow registry a deployment overrides. Keyed by track.
WORKFLOWS: dict[DisputeTrack, WorkflowDefinition] = {
    DisputeTrack.CARD_SCHEME: CARD_SCHEME_WORKFLOW,
    DisputeTrack.RETAIL: RETAIL_WORKFLOW,
}


def workflow_for(track: DisputeTrack) -> WorkflowDefinition:
    """The workflow for a track, or ``KeyError`` (fail closed) for an unregistered one."""
    return WORKFLOWS[track]
