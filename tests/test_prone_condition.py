"""Behavioral coverage for the complete Prone condition slice."""

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.prone_state import apply_shared_space_prone
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.geometry import MovementBudget
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    TACTICAL_ENCOUNTER_DIR,
    choose_advertised_action,
)


def _session() -> Session:
    session = Session(load_encounter_directory(TACTICAL_ENCOUNTER_DIR))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("player")
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position.x = 7 + index
        state.creatures[target_ref].position.y = 7
    return session


def _apply_prone(session: Session, creature_ref: str = "player") -> None:
    state = session.encounter_state
    assert state is not None
    result = apply_condition(
        state,
        build_applied_condition(
            condition=Condition.PRONE,
            source_ref="test:fall",
            source_label="Test fall",
            target_ref=creature_ref,
        ),
    )
    assert result.accepted


def test_prone_creature_can_crawl_at_double_cost() -> None:
    session = _session()
    _apply_prone(session)
    state = session.encounter_state
    assert state is not None
    move = next(action for action in state.available_actions() if action.kind == "move")

    assert int(move.cost.movement) == 2
    choose_advertised_action(session, move)

    actor = state.creatures["player"]
    assert actor.movement_remaining == 4
    assert actor.movement_spent_this_turn == 2
    assert state.has_condition("player", Condition.PRONE)


def test_standing_spends_half_speed_without_spending_an_action() -> None:
    session = _session()
    _apply_prone(session)
    state = session.encounter_state
    assert state is not None
    second = build_applied_condition(
        condition=Condition.PRONE,
        source_ref="test:second_fall",
        source_label="Second test fall",
        target_ref="player",
        origin_id="test:second-fall",
    )
    assert apply_condition(state, second).accepted
    assert len(state.conditions_for("player")) == 2
    stand = next(
        action for action in state.available_actions() if action.kind == "stand_up"
    )

    assert int(stand.cost.movement) == 3
    choose_advertised_action(session, stand)

    actor = state.creatures["player"]
    assert actor.movement_remaining == 3
    assert actor.movement_spent_this_turn == 3
    assert actor.actions_remaining == 1
    assert state.has_condition("player", Condition.PRONE) is False


def test_standing_is_unavailable_without_half_speed_remaining() -> None:
    session = _session()
    _apply_prone(session)
    state = session.encounter_state
    assert state is not None
    state.creatures["player"].movement_remaining = MovementBudget(2)

    observation = session.observe()
    stand = next(
        action
        for action in observation.scene.action_details
        if action.kind == "stand_up"
    )

    assert stand.enabled is False
    assert {reason.code for reason in stand.reasons} == {"insufficient_movement"}


def test_creature_can_drop_prone_without_spending_movement_or_an_action() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    drop = next(
        action for action in state.available_actions() if action.kind == "drop_prone"
    )

    choose_advertised_action(session, drop)

    actor = state.creatures["player"]
    assert actor.movement_remaining == 6
    assert actor.movement_spent_this_turn == 0
    assert actor.actions_remaining == 1
    assert state.has_condition("player", Condition.PRONE)


def test_speed_zero_advertises_standing_as_unavailable() -> None:
    session = _session()
    _apply_prone(session)
    state = session.encounter_state
    assert state is not None
    grappled = build_applied_condition(
        condition=Condition.GRAPPLED,
        source_ref="goblin_1",
        source_label="Goblin",
        target_ref="player",
    )
    assert apply_condition(state, grappled).accepted

    observation = session.observe()
    stand = next(
        action
        for action in observation.scene.action_details
        if action.kind == "stand_up"
    )

    assert stand.enabled is False
    assert {reason.code for reason in stand.reasons} == {"condition.prone_speed_zero"}


def test_prone_attack_modifiers_depend_on_attacker_and_distance() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    attacker = state.creatures["player"]
    target = state.creatures["goblin_1"]
    target.position.x = attacker.position.x + 1
    target.position.y = attacker.position.y

    _apply_prone(session, "player")
    assert (
        attack_roll_mode_for(
            state,
            "player",
            "goblin_1",
            "melee",
            attacker.position,
            (),
        )
        == "disadvantage"
    )

    state.conditions.clear()
    _apply_prone(session, "goblin_1")
    assert (
        attack_roll_mode_for(
            state,
            "player",
            "goblin_1",
            "melee",
            attacker.position,
            (),
        )
        == "advantage"
    )

    target.position.x = attacker.position.x + 2
    assert (
        attack_roll_mode_for(
            state,
            "player",
            "goblin_1",
            "ranged",
            attacker.position,
            (),
        )
        == "disadvantage"
    )


def test_ending_turn_in_a_shared_space_applies_prone() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    state.creatures["goblin_1"].position = state.creatures["player"].position
    state.creatures["goblin_1"].creature.size = "M"
    wait = next(action for action in state.available_actions() if action.kind == "wait")

    choose_advertised_action(session, wait)

    assert state.has_condition("player", Condition.PRONE)


def test_tiny_or_larger_creature_is_exempt_from_shared_space_prone() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["player"]
    other = state.creatures["goblin_1"]
    other.position = actor.position

    actor.creature.size = "T"
    assert apply_shared_space_prone(state, "player") is False

    actor.creature.size = "L"
    other.creature.size = "M"
    assert apply_shared_space_prone(state, "player") is False
