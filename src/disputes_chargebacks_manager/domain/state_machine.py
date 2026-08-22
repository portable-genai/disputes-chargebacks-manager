"""The deterministic dispute state machine: transition legality and lifecycle replay.

Pure stdlib. It reads a :class:`~.workflows.WorkflowDefinition` and answers exactly two
questions: is a move legal, and what sequence of states does a sequence of triggers produce. It
NEVER guesses: an illegal move raises rather than silently staying put, and an unknown trigger
raises rather than being ignored. This is the property the lifecycle-trace eval metric checks
against an independently declared golden journey.
"""

from __future__ import annotations

from .models import DisputeState
from .workflows import WorkflowDefinition


class IllegalTransitionError(ValueError):
    """Raised when a trigger names no legal move from the current state (fail closed)."""


def can_transition(
    workflow: WorkflowDefinition, source: DisputeState, target: DisputeState
) -> bool:
    """True only when ``source -> target`` is a declared transition of ``workflow``."""
    return target in workflow.legal_targets(source)


def apply_trigger(workflow: WorkflowDefinition, source: DisputeState, trigger: str) -> DisputeState:
    """Return the state reached by ``trigger`` from ``source``, or raise if none is legal.

    The match is exact on both source and trigger: an unknown trigger, or a trigger legal only
    from a different state, raises :class:`IllegalTransitionError`. A terminal source raises too,
    because there is no legal move out of a closed dispute.
    """
    if workflow.is_terminal(source):
        raise IllegalTransitionError(
            f"{source.value} is terminal; no trigger applies (attempted {trigger!r})"
        )
    for transition in workflow.transitions:
        if transition.source == source and transition.trigger == trigger:
            return transition.target
    legal = ", ".join(sorted(t.trigger for t in workflow.transitions if t.source == source))
    raise IllegalTransitionError(
        f"trigger {trigger!r} is not legal from {source.value}; legal triggers: {legal or 'none'}"
    )


def replay(workflow: WorkflowDefinition, triggers: tuple[str, ...]) -> tuple[DisputeState, ...]:
    """Replay ``triggers`` from the workflow's initial state, returning the states visited.

    The returned tuple includes the initial state, so a run of N triggers yields N+1 states. Any
    illegal trigger raises at the point it occurs, so a golden journey either replays exactly or
    fails loudly; there is no partial-credit path.
    """
    state = workflow.initial
    visited = [state]
    for trigger in triggers:
        state = apply_trigger(workflow, state, trigger)
        visited.append(state)
    return tuple(visited)
