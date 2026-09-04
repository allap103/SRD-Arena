"""Behavioral coverage for the complete Restrained condition slice."""

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.rule_queries.rolls import roll_modifiers
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import TACTICAL_ENCOUNTER_DIR


def _session() -> Session:
    session = Session(load_encounter_directory(TACTICAL_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("player")
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position.x = 7 + index
        state.creatures[target_ref].position.y = 7
    return session


def _apply_restrained(session: Session, creature_ref: str = "player") -> str:
    state = session.encounter_state
    assert state is not None
    restrained = build_applied_condition(
        condition=Condition.RESTRAINED,
        source_ref="test:web",
        source_label="Test web",
        target_ref=creature_ref,
    )
    result = apply_condition(state, restrained)
    assert result.accepted
    return restrained.id


def test_restrained_creature_advertises_movement_as_unavailable() -> None:
    session = _session()
    _apply_restrained(session)

    movement = [
        action
        for action in session.observe().scene.action_details
        if action.kind == "move"
    ]

    assert movement
    assert all(action.enabled is False for action in movement)
    assert all(
        "movement.speed_zero" in {reason.code for reason in action.reasons}
        for action in movement
    )


def test_restrained_applies_both_attack_roll_consequences() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    attacker = state.creatures["player"]
    target = state.creatures["goblin_1"]
    target.position.x = attacker.position.x + 1
    target.position.y = attacker.position.y

    _apply_restrained(session, "player")
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
    _apply_restrained(session, "goblin_1")
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


def test_restrained_gives_only_dexterity_saves_disadvantage() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    provider_id = _apply_restrained(session)

    dexterity = roll_modifiers(
        state,
        "player",
        "saving_throw",
        ability="dexterity",
    )
    wisdom = roll_modifiers(
        state,
        "player",
        "saving_throw",
        ability="wisdom",
    )

    assert dexterity.mode == "disadvantage"
    assert tuple(
        contribution.provider_state_id for contribution in dexterity.contributions
    ) == (provider_id,)
    assert wisdom.mode == "normal"
