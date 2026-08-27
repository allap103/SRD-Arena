from pathlib import Path

import pytest

from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.effects import EffectResult, TriggeredEffect
from srd_arena.domain.effects.application import condition_from_effect
from srd_arena.infrastructure.scenarios import load_scenario_directory
from srd_arena.engine.session import Session


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
    scenario = load_scenario_directory(
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
    session = load_scenario_directory(
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
    scenario = load_scenario_directory(
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
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
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
    assert state.pending_movement is not None
    assert state.pending_movement.creature_ref == "champion_2"
    assert state.pending_movement.direction == "up"
    assert (
        state.pending_movement.to_position.x,
        state.pending_movement.to_position.y,
    ) == (3, 2)
    exported = state.export_state()
    exported_decision = exported["decision"]
    exported_movement = exported["pending_movement"]
    assert isinstance(exported_decision, dict)
    assert isinstance(exported_movement, dict)
    assert (
        exported_decision["pending_movement_id"]
        == state.pending_movement.action_id
    )
    assert exported_movement["action_id"] == state.pending_movement.action_id
    assert "pending_action" not in exported
    assert (mover.position.x, mover.position.y) == (3, 3)
    assert not any(event.type == "movement_resolved" for event in interrupted.events)

    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    resumed = session.choose_encounter_action(opportunity_attack)

    assert state.pending_movement is None
    assert state.current_decision().kind == "turn"
    assert state.current_decision().creature_ref == "champion_2"
    assert (mover.position.x, mover.position.y) == (3, 2)
    assert reactor.reaction_available is False
    movement = next(
        event for event in resumed.events if event.type == "movement_resolved"
    )
    assert movement.creature_ref == "champion_2"
    assert movement.data["resumed"] is True


def test_lethal_reaction_closes_the_frame_without_resuming_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda _count, sides: sides,
    )
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("champion_2")
    mover = state.creatures["champion_2"]
    reactor = state.creatures["red_blade"]
    mover.creature.current_health = 1
    mover.position.x, mover.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )

    session.choose_encounter_action(move)
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    resolved = session.choose_encounter_action(opportunity_attack)

    assert mover.is_alive is False
    assert (mover.position.x, mover.position.y) == (3, 3)
    assert state.decision_stack == []
    assert state.pending_movement is None
    assert not any(event.type == "movement_resolved" for event in resolved.events)


def test_nested_damage_reroll_closes_in_lifo_order_before_movement_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 15,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda _count, _sides: 1,
    )
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("champion_2")
    mover = state.creatures["champion_2"]
    reactor = state.creatures["red_blade"]
    mover.position.x, mover.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    reactor.creature.triggered_effects.append(
        TriggeredEffect(
            id="test_damage_reroll",
            source_type="test",
            source_id="test",
            trigger="weapon_damage_rolled",
            operation="reroll_matching_dice",
            parameters={"values": [1], "maximum_per_die": 2},
        )
    )
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )

    session.choose_encounter_action(move)
    reaction_frame = state.current_decision()
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    interrupted_again = session.choose_encounter_action(opportunity_attack)

    assert interrupted_again.decision is not None
    assert interrupted_again.decision["kind"] == "reroll_dice"
    assert [frame.kind for frame in state.decision_stack] == [
        "reaction",
        "reroll_dice",
    ]
    reroll_frame = state.current_decision()
    reroll = next(
        action for action in state.available_actions() if action.kind == "reroll_die"
    )

    still_interrupted = session.choose_encounter_action(reroll)

    assert still_interrupted.decision is not None
    assert still_interrupted.decision["frame_id"] == reroll_frame.id
    assert [frame.id for frame in state.decision_stack] == [
        reaction_frame.id,
        reroll_frame.id,
    ]
    assert state.pending_movement is not None
    assert (mover.position.x, mover.position.y) == (3, 3)
    assert not any(
        event.type in {"decision_closed", "movement_resolved"}
        for event in still_interrupted.events
    )
    accept_damage = next(
        action for action in state.available_actions() if action.kind == "accept_roll"
    )

    resumed = session.choose_encounter_action(accept_damage)

    assert state.decision_stack == []
    assert state.pending_movement is None
    assert (mover.position.x, mover.position.y) == (3, 2)
    closed_frame_ids = [
        event.frame_id for event in resumed.events if event.type == "decision_closed"
    ]
    assert closed_frame_ids == [reroll_frame.id, reaction_frame.id]
    movement_event_index = next(
        index
        for index, event in enumerate(resumed.events)
        if event.type == "movement_resolved"
    )
    parent_close_index = next(
        index
        for index, event in enumerate(resumed.events)
        if event.type == "decision_closed" and event.frame_id == reaction_frame.id
    )
    assert parent_close_index < movement_event_index


def test_passing_reaction_closes_it_before_parent_movement_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
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

    session.choose_encounter_action(move)
    reaction_frame = state.current_decision()
    assert state.pending_movement is not None
    movement_action_id = state.pending_movement.action_id
    pass_reaction = next(
        action for action in state.available_actions() if action.kind == "pass"
    )
    resumed = session.choose_encounter_action(pass_reaction)

    assert state.decision_stack == []
    assert state.pending_movement is None
    assert state.current_decision().creature_ref == "champion_2"
    assert (mover.position.x, mover.position.y) == (3, 2)
    assert reactor.reaction_available is True
    relevant_events = [
        event
        for event in resumed.events
        if event.type in {"decision_closed", "movement_resolved", "attack_resolved"}
    ]
    assert [event.type for event in relevant_events] == [
        "decision_closed",
        "movement_resolved",
    ]
    assert relevant_events[0].frame_id == reaction_frame.id
    assert relevant_events[1].action_id == movement_action_id


def test_resumed_movement_carries_a_grappled_creature() -> None:
    session = load_scenario_directory(FULL_CONTROL_SCENARIO_DIR).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    state.turn_index = state.initiative_order.index("champion_2")
    mover = state.creatures["champion_2"]
    grappled = state.creatures["red_archer"]
    reactor = state.creatures["red_blade"]
    mover.position.x, mover.position.y = 3, 3
    grappled.position.x, grappled.position.y = 4, 3
    reactor.position.x, reactor.position.y = 3, 4
    state._apply_grapple(
        condition_from_effect(
            EffectResult(
                kind="apply_condition",
                target_ref="red_archer",
                data={
                    "condition": "grappled",
                    "source_ref": "champion_2",
                    "source_label": mover.creature.name,
                },
            )
        )
    )
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )

    session.choose_encounter_action(move)
    assert state.pending_movement is not None
    assert state.pending_movement.companion_destinations["red_archer"].x == 4
    assert state.pending_movement.companion_destinations["red_archer"].y == 2
    pass_reaction = next(
        action for action in state.available_actions() if action.kind == "pass"
    )
    session.choose_encounter_action(pass_reaction)

    assert (mover.position.x, mover.position.y) == (3, 2)
    assert (grappled.position.x, grappled.position.y) == (4, 2)


def test_reaction_to_scripted_movement_resumes_automatic_advancement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    scenario = load_scenario_directory(
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
    assert state.pending_movement is not None
    assert state.pending_movement.creature_ref == "goblin_2"
    assert state.pending_movement.direction == "up-right"
    assert (
        state.pending_movement.to_position.x,
        state.pending_movement.to_position.y,
    ) == (4, 2)
    assert (mover.position.x, mover.position.y) == (3, 3)

    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    resumed = session.choose_encounter_action(opportunity_attack)

    assert state.pending_movement is None
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
