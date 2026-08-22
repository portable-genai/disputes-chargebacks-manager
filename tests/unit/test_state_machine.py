"""The deterministic dispute state machine: legality, replay, fail-closed on illegal moves."""

from __future__ import annotations

import pytest

from disputes_chargebacks_manager.domain.models import DisputeState
from disputes_chargebacks_manager.domain.state_machine import (
    IllegalTransitionError,
    apply_trigger,
    can_transition,
    replay,
)
from disputes_chargebacks_manager.domain.workflows import (
    CARD_SCHEME_WORKFLOW,
    RETAIL_WORKFLOW,
)


def test_a_legal_move_is_accepted_and_an_illegal_one_is_refused() -> None:
    assert can_transition(CARD_SCHEME_WORKFLOW, DisputeState.INTAKE, DisputeState.ELIGIBILITY_CHECK)
    assert not can_transition(CARD_SCHEME_WORKFLOW, DisputeState.INTAKE, DisputeState.ARBITRATION)


def test_apply_trigger_follows_the_declared_transition() -> None:
    assert (
        apply_trigger(CARD_SCHEME_WORKFLOW, DisputeState.INTAKE, "submit")
        is DisputeState.ELIGIBILITY_CHECK
    )
    assert (
        apply_trigger(CARD_SCHEME_WORKFLOW, DisputeState.ELIGIBILITY_CHECK, "ineligible")
        is DisputeState.REJECTED
    )


def test_an_unknown_trigger_raises_rather_than_staying_put() -> None:
    with pytest.raises(IllegalTransitionError):
        apply_trigger(CARD_SCHEME_WORKFLOW, DisputeState.INTAKE, "teleport")


def test_a_terminal_state_admits_no_trigger() -> None:
    with pytest.raises(IllegalTransitionError):
        apply_trigger(CARD_SCHEME_WORKFLOW, DisputeState.CLOSED_WON, "submit")


def test_replay_reconstructs_a_golden_card_journey() -> None:
    """A representment journey replays to exactly the declared states, initial included."""
    states = replay(CARD_SCHEME_WORKFLOW, ("submit", "eligible", "contest", "represented"))
    assert states == (
        DisputeState.INTAKE,
        DisputeState.ELIGIBILITY_CHECK,
        DisputeState.EVIDENCE_REVIEW,
        DisputeState.REPRESENTMENT,
        DisputeState.CLOSED_WON,
    )


def test_replay_of_a_retail_refund_journey() -> None:
    states = replay(RETAIL_WORKFLOW, ("submit", "eligible", "refund_approved", "close"))
    assert states[-1] is DisputeState.CLOSED_LOST


def test_replay_fails_loudly_on_an_illegal_step_no_partial_credit() -> None:
    with pytest.raises(IllegalTransitionError):
        replay(CARD_SCHEME_WORKFLOW, ("submit", "escalate"))


def test_every_transition_names_states_the_workflow_declares() -> None:
    """A transition to or from an undeclared state is a data bug the engine would trust."""
    for workflow in (CARD_SCHEME_WORKFLOW, RETAIL_WORKFLOW):
        declared = set(workflow.states)
        for transition in workflow.transitions:
            assert transition.source in declared
            assert transition.target in declared
