from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.rule_effects import OpportunityAttackPrevention
from srd_arena.domain.encounters.rule_queries.providers import ongoing_rule_effects
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import choose_advertised_action

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
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("champion_2")
    state.creatures["champion_2"].position.x = 3
    state.creatures["champion_2"].position.y = 3
    state.creatures["red_blade"].position.x = 3
    state.creatures["red_blade"].position.y = 4
    return session


def test_disengage_spends_the_action_and_prevents_opportunity_attacks() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None

    disengage = next(
        action for action in state.available_actions() if action.kind == "disengage"
    )
    result = choose_advertised_action(session, disengage)

    assert state.active_actions_remaining == 0
    assert any(
        isinstance(rule_effect, OpportunityAttackPrevention)
        for _state_id, _source, rule_effect in ongoing_rule_effects(
            state,
            "champion_2",
        )
    )
    assert any(
        event.type == "action_resolved" and event.data["kind"] == "disengage"
        for event in result.events
    )

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    moved = choose_advertised_action(session, move)

    assert state.current_decision().kind == "turn"
    assert state.current_decision().creature_ref == "champion_2"
    assert (state.active_position.x, state.active_position.y) == (3, 2)
    assert state.creatures["red_blade"].reaction_available is True
    assert not any(event.type == "trigger_opened" for event in moved.events)


def test_disengage_expires_at_the_end_of_the_creatures_turn() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    disengage = next(
        action for action in state.available_actions() if action.kind == "disengage"
    )
    choose_advertised_action(session, disengage)

    wait = next(action for action in state.available_actions() if action.kind == "wait")
    choose_advertised_action(session, wait)

    assert not any(
        effect.identity.source.definition_id == "disengage"
        for effect in state.ongoing_effects
    )


def test_nimble_escape_grants_disengage_as_a_bonus_action() -> None:
    session = Session(load_encounter_directory(ENCOUNTER_DIR))
    session._read()
    state = session.encounter_state
    assert state is not None
    state.turn.index = state.initiative_order.index("red_blade")
    goblin = state.creatures["red_blade"]
    fighter = state.creatures["champion_2"]
    goblin.position.x, goblin.position.y = 3, 3
    fighter.position.x, fighter.position.y = 3, 4

    options = session._read().action_options
    nimble_disengage = next(
        option for option in options if option.label == "Nimble Escape  Disengage"
    )
    nimble_hide = next(
        option for option in options if option.label == "Nimble Escape  Hide"
    )

    assert nimble_disengage.enabled is True
    assert nimble_disengage.cost.action == 0
    assert nimble_disengage.cost.bonus_action == 1
    assert nimble_hide.availability == "unimplemented"
    assert nimble_hide.eligibility.failures[0].code == "unsupported_standard_action"

    nimble_action = next(
        action
        for action in state.available_actions()
        if action.id == nimble_disengage.id
    )
    choose_advertised_action(session, nimble_action)

    assert state.active_actions_remaining == 1
    assert state.active_bonus_action_available is False
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    moved = choose_advertised_action(session, move)

    assert (goblin.position.x, goblin.position.y) == (3, 2)
    assert fighter.reaction_available is True
    assert not any(event.type == "trigger_opened" for event in moved.events)
