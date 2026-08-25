from pathlib import Path

from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.models import ActionExecutionOutcome
from srd_arena.runtime.scenario import Scenario


FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
_ORCHESTRATOR = EncounterOrchestrator()


def _encounter_state():
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    external_ref = next(
        creature_ref
        for creature_ref in state.initiative_order
        if state._creature_controller(creature_ref) == "external"
    )
    state.turn_index = state.initiative_order.index(external_ref)
    return state


def test_action_execution_reports_lifecycle_without_advancing_turn() -> None:
    state = _encounter_state()
    decision = state.current_decision()
    wait = next(action for action in state.available_actions() if action.kind == "wait")
    starting_turn = state.turn_index

    result = state._execute_creature_action(wait, decision)

    assert result.outcome is ActionExecutionOutcome.END_TURN
    assert state.turn_index == starting_turn
    assert [event.type for event in result.progress.events] == [
        "action_declared",
        "action_resolved",
    ]


def test_orchestrator_interprets_end_turn_outcome() -> None:
    state = _encounter_state()
    wait = next(action for action in state.available_actions() if action.kind == "wait")
    starting_round = state.round.number

    progress = _ORCHESTRATOR.submit(state, wait)

    assert progress.events[0].type == "action_declared"
    assert state.round.number > starting_round


def test_non_terminal_action_reports_continue_turn() -> None:
    state = _encounter_state()
    decision = state.current_decision()
    move = next(action for action in state.available_actions() if action.kind == "move")
    starting_turn = state.turn_index

    result = state._execute_creature_action(move, decision)

    assert result.outcome is ActionExecutionOutcome.CONTINUE_TURN
    assert state.turn_index == starting_turn
    assert result.progress.events[0].type == "action_declared"
    assert result.progress.events[-1].type == "movement_resolved"
