from pathlib import Path

import pytest

from srd_arena.domain.encounters.continuations import ContinuationRunner
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.models import (
    CloseParentDecision,
    DecisionFrame,
    EncounterProgress,
)
from srd_arena.infrastructure.scenarios import load_scenario_directory

FULL_CONTROL_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)


def _encounter_state() -> EncounterState:
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    return session.encounter_state


def test_continuation_runner_rejects_out_of_order_completion() -> None:
    state = _encounter_state()
    parent = DecisionFrame(
        id="parent",
        creature_ref="champion_2",
        kind="reaction",
        reason="test",
    )
    child = DecisionFrame(
        id="child",
        creature_ref="red_blade",
        kind="reaction",
        reason="test",
        parent_frame_id=parent.id,
    )
    state.decision_stack = [parent, child]
    progress = EncounterProgress()

    with pytest.raises(
        RuntimeError,
        match="Cannot close decision 'parent' while 'child' is active",
    ):
        ContinuationRunner().complete_decision(
            state,
            parent,
            action_id="test-action",
            progress=progress,
        )

    assert state.decision_stack == [parent, child]
    assert progress.events == []


def test_continuation_runner_rejects_an_unrelated_parent_without_mutation() -> None:
    state = _encounter_state()
    parent = DecisionFrame(
        id="parent",
        creature_ref="champion_2",
        kind="reaction",
        reason="test",
    )
    child = DecisionFrame(
        id="child",
        creature_ref="red_blade",
        kind="reroll_dice",
        reason="test",
        parent_frame_id=parent.id,
        continuation=CloseParentDecision(
            frame_id="different-parent",
            action_id="test-action",
        ),
    )
    state.decision_stack = [parent, child]
    progress = EncounterProgress()

    with pytest.raises(RuntimeError, match="cannot complete unrelated frame"):
        ContinuationRunner().complete_decision(
            state,
            child,
            action_id="test-action",
            progress=progress,
        )

    assert state.decision_stack == [parent, child]
    assert progress.events == []
