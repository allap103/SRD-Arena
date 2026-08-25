from pathlib import Path

import pytest

from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.runtime.scenario import Scenario
from srd_arena.runtime.session import Session


TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
FULL_CONTROL_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)
_ORCHESTRATOR = EncounterOrchestrator()


@pytest.fixture(autouse=True)
def _stable_initiative(monkeypatch: pytest.MonkeyPatch) -> None:
    def _use_definition_order(state: EncounterState) -> None:
        state.initiative_entries = []
        state.initiative_order = list(state.creatures)

    monkeypatch.setattr(EncounterState, "_roll_initiative", _use_definition_order)


def _all_external_session() -> Session:
    scenario = Scenario(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    )
    for team in scenario.encounters["goblin_encounter"].teams:
        team.controller = "external"
    session = scenario.create_session()
    session.get_scene_view()
    return session


def test_manual_action_submission_returns_to_the_same_turn_until_wait() -> None:
    session = _all_external_session()
    state = session.encounter_state
    assert state is not None
    actor_ref = state.current_decision().creature_ref
    start = (state.active_position.x, state.active_position.y)
    move = next(action for action in state.available_actions() if action.kind == "move")

    moved = session.choose_encounter_action(move)

    assert moved.selected_action_id == move.id
    assert moved.decision is not None
    assert moved.decision["kind"] == "turn"
    assert moved.decision["creature_ref"] == actor_ref
    assert state.current_decision().creature_ref == actor_ref
    assert (state.active_position.x, state.active_position.y) != start
    assert state.active_movement_remaining == 5

    wait = next(action for action in state.available_actions() if action.kind == "wait")
    ended = session.choose_encounter_action(wait)

    assert ended.decision is not None
    assert ended.decision["creature_ref"] == "goblin_1"
    assert state.current_decision().creature_ref == "goblin_1"


def test_scripted_turns_advance_until_the_next_external_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    session = Scenario(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    wait = next(action for action in state.available_actions() if action.kind == "wait")

    result = session.choose_encounter_action(wait)

    assert result.decision is not None
    assert result.decision["kind"] == "turn"
    assert result.decision["creature_ref"] == "player"
    assert state.current_decision().creature_ref == "player"
    assert state.requires_automatic_advance() is False
    scripted_actors = {
        event.creature_ref
        for event in result.events
        if event.type == "action_declared" and event.creature_ref != "player"
    }
    assert scripted_actors == {"goblin_1", "goblin_2", "goblin_3"}


def test_pacing_pause_skips_defeated_initiative_slots_first() -> None:
    scenario = Scenario(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    )
    goblin = next(
        participant
        for participant in scenario.encounters["goblin_encounter"].participants
        if participant.creature_id == "goblin_1"
    )
    assert goblin.behavior is not None
    goblin.behavior.type = "wait"
    session = scenario.create_session()
    session.automatic_action_limit = 1
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("goblin_1")
    state.creatures["goblin_2"].creature.current_health = 0

    progress = _ORCHESTRATOR.advance(state)

    assert progress.paused_for_pacing is True
    assert state.current_decision().creature_ref == "goblin_3"


def test_querying_a_defeated_actors_decision_does_not_advance_the_turn() -> None:
    session = _all_external_session()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("goblin_1")
    state.creatures["goblin_1"].creature.current_health = 0
    turn_index = state.turn_index
    round_number = state.round.number

    decision = state.current_decision()

    assert decision.creature_ref == "goblin_1"
    assert state.turn_index == turn_index
    assert state.round.number == round_number

    progress = _ORCHESTRATOR.advance(state)

    assert progress.paused_for_decision is True
    assert state.turn_index == turn_index + 1
    assert state.round.number == round_number
    assert state.current_decision().creature_ref == "goblin_2"


def test_reaction_interrupts_movement_then_resumes_the_parent_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    session = Scenario(FULL_CONTROL_SCENARIO_DIR).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("champion_2")
    mover = state.creatures["champion_2"]
    reactor = state.creatures["red_blade"]
    mover.position.x, mover.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )

    interrupted = session.choose_encounter_action(move)

    assert interrupted.decision is not None
    assert interrupted.decision["kind"] == "reaction"
    assert interrupted.decision["creature_ref"] == "red_blade"
    assert state.pending_action is not None
    assert state.pending_action.creature_ref == "champion_2"
    assert state.pending_action.direction == "up"
    assert (
        state.pending_action.to_position.x,
        state.pending_action.to_position.y,
    ) == (3, 2)
    assert (mover.position.x, mover.position.y) == (3, 3)
    assert not any(event.type == "movement_resolved" for event in interrupted.events)

    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    resumed = session.choose_encounter_action(opportunity_attack)

    assert state.pending_action is None
    assert state.current_decision().kind == "turn"
    assert state.current_decision().creature_ref == "champion_2"
    assert (mover.position.x, mover.position.y) == (3, 2)
    assert reactor.reaction_available is False
    movement = next(
        event for event in resumed.events if event.type == "movement_resolved"
    )
    assert movement.creature_ref == "champion_2"
    assert movement.data["resumed"] is True


def test_reaction_to_scripted_movement_resumes_automatic_advancement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    scenario = Scenario(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    )
    goblin = next(
        participant
        for participant in scenario.encounters["goblin_encounter"].participants
        if participant.creature_id == "goblin_2"
    )
    assert goblin.behavior is not None
    goblin.behavior.type = "guard"
    session = scenario.create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("goblin_2")
    mover = state.creatures["goblin_2"]
    reactor = state.creatures["player"]
    mover.position.x, mover.position.y = 3, 3
    mover.actions_remaining = 0
    reactor.position.x, reactor.position.y = 3, 4

    interrupted = session.advance_until_input_required()

    assert interrupted.decision is not None
    assert interrupted.decision["kind"] == "reaction"
    assert interrupted.decision["creature_ref"] == "player"
    assert state.pending_action is not None
    assert state.pending_action.creature_ref == "goblin_2"
    assert state.pending_action.direction == "up-right"
    assert (
        state.pending_action.to_position.x,
        state.pending_action.to_position.y,
    ) == (4, 2)
    assert (mover.position.x, mover.position.y) == (3, 3)

    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    resumed = session.choose_encounter_action(opportunity_attack)

    assert state.pending_action is None
    assert resumed.decision is not None
    assert resumed.decision["kind"] == "turn"
    assert resumed.decision["creature_ref"] == "player"
    assert state.current_decision().creature_ref == "player"
    assert (mover.position.x, mover.position.y) != (3, 3)
    assert any(
        event.type == "movement_resolved"
        and event.creature_ref == "goblin_2"
        and event.data.get("resumed") is True
        for event in resumed.events
    )
    assert any(
        event.type == "action_declared" and event.creature_ref == "goblin_3"
        for event in resumed.events
    )
