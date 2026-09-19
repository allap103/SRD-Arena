"""Exercise the shared Hide and Search action lifecycle."""

from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters.rule_queries.visibility import (
    creature_can_see_creature,
)
from srd_arena.domain.encounters.terrain import CoverDegree, TerrainCell
from srd_arena.domain.geometry import Position
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    as_mapping,
    choose_advertised_action,
    use_deterministic_dice,
)

ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "full_control_showcase"
)


def _session() -> Session:
    session = Session(load_encounter_directory(ENCOUNTER_DIR))
    session._read()
    state = session.encounter_state
    assert state is not None
    state.turn.index = state.initiative_order.index("red_blade")
    for creature_ref in ("player", "red_archer", "blue_blade", "blue_archer"):
        state.creatures[creature_ref].creature.current_health = 0
    state.creatures["red_blade"].position = Position(3, 2)
    state.creatures["champion_2"].position = Position(3, 4)
    state.definition.terrain = (TerrainCell(Position(3, 3), cover=CoverDegree.TOTAL),)
    use_deterministic_dice(session, die_roller=lambda _sides: 10)
    return session


def _hide_with_nimble_escape(session: Session) -> None:
    state = session.encounter_state
    assert state is not None
    option = next(
        option
        for option in session._read().action_options
        if option.kind == "hide" and option.cost.bonus_action == 1
    )
    action = next(
        action for action in state.available_actions() if action.id == option.id
    )
    choose_advertised_action(session, action)


def test_nimble_escape_hide_applies_sourced_invisibility_as_a_bonus_action() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None

    option = next(
        option
        for option in session._read().action_options
        if option.kind == "hide" and option.cost.bonus_action == 1
    )
    assert option.label == "Nimble Escape — Hide"
    assert option.enabled is True

    action = next(
        action for action in state.available_actions() if action.id == option.id
    )
    result = choose_advertised_action(session, action)

    assert state.active_actions_remaining == 1
    assert state.active_bonus_action_available is False
    assert state.effective_conditions_for("red_blade").has(Condition.INVISIBLE)
    hidden = next(
        condition
        for condition in state.conditions_for("red_blade")
        if condition.metadata.get("hidden") is True
    )
    assert hidden.metadata["stealth_total"] == 16
    assert creature_can_see_creature(state, "champion_2", "red_blade") is False
    event = next(
        event
        for event in result.events
        if event.type == "action_resolved" and event.data["kind"] == "hide"
    )
    assert event.data["success"] is True
    assert as_mapping(event.data["roll_detail"])["mode"] == "normal"


def test_hidden_attack_has_advantage_and_then_ends_hide() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    _hide_with_nimble_escape(session)
    state.definition.terrain = ()
    state.creatures["champion_2"].position = Position(3, 3)

    attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack"
        and action.value == "champion_2"
        and action.preferred_attack_name == "Scimitar"
    )
    result = choose_advertised_action(session, attack)

    event = next(event for event in result.events if event.type == "attack_resolved")
    assert as_mapping(event.data["attack_roll_detail"])["mode"] == "advantage"
    assert state.effective_conditions_for("red_blade").has(Condition.INVISIBLE) is False
    assert not any(
        effect.identity.source.definition_id == "hide"
        for effect in state.ongoing_effects
    )


def test_successful_search_ends_an_opponents_hide() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    _hide_with_nimble_escape(session)
    state.definition.terrain = ()
    state.turn.index = state.initiative_order.index("champion_2")
    use_deterministic_dice(session, die_roller=lambda _sides: 20)

    search = next(
        action
        for action in state.available_actions()
        if action.kind == "search_hidden" and action.value == "red_blade"
    )
    result = choose_advertised_action(session, search)

    assert state.active_actions_remaining == 0
    assert state.effective_conditions_for("red_blade").has(Condition.INVISIBLE) is False
    event = next(
        event
        for event in result.events
        if event.type == "action_resolved" and event.data["kind"] == "search_hidden"
    )
    assert event.data["success"] is True
    assert event.data["dc"] == 16
