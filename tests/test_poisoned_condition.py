"""Behavioral coverage for the complete Poisoned condition slice."""

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.encounters.rule_queries.rolls import roll_modifiers
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    TACTICAL_ENCOUNTER_DIR,
    action_id,
    action_id_by_label,
    use_deterministic_dice,
)


def _session() -> Session:
    session = Session(load_encounter_directory(TACTICAL_ENCOUNTER_DIR))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("player")
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    return session


def _apply_poisoned(session: Session, creature_ref: str = "player") -> str:
    state = session.encounter_state
    assert state is not None
    poisoned = build_applied_condition(
        condition=Condition.POISONED,
        source_ref="test:venom",
        source_label="Test venom",
        target_ref=creature_ref,
    )
    result = apply_condition(state, poisoned)
    assert result.accepted
    return poisoned.id


def test_poisoned_creature_has_disadvantage_on_outgoing_attacks() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    attacker = state.creatures["player"]
    _apply_poisoned(session)

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


def test_poisoned_creature_has_disadvantage_on_every_ability_check() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    provider_id = _apply_poisoned(session)

    for ability in ("strength", "dexterity", "constitution", "intelligence"):
        result = roll_modifiers(
            state,
            "player",
            "ability_check",
            ability=ability,
        )
        assert result.mode == "disadvantage"
        assert tuple(
            contribution.provider_state_id for contribution in result.contributions
        ) == (provider_id,)


def test_poisoned_disadvantage_is_used_by_grapple_escape_checks() -> None:
    session = _session()
    _apply_poisoned(session)
    state = session.encounter_state
    assert state is not None
    grapple = build_applied_condition(
        condition=Condition.GRAPPLED,
        source_ref="goblin_1",
        source_label="Goblin Warrior",
        target_ref="player",
        metadata={"escape_dc": 30},
    )
    assert apply_grapple(state, grapple).accepted
    rolls = iter((20, 1))
    use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    result = session.choose(
        action_id_by_label(
            session,
            "Escape Goblin Warrior with Athletics (DC 30)",
        )
    )

    escape = next(event for event in result.events if event.type == "action_resolved")
    assert escape.data["success"] is False
    assert escape.data["roll_detail"] == {
        "dice": [20, 1],
        "mode": "disadvantage",
        "modifier": 4,
        "total": 5,
    }


def test_poisoned_and_stunned_attack_modes_cancel_once() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    _apply_poisoned(session)
    stunned = build_applied_condition(
        condition=Condition.STUNNED,
        source_ref="test:spell",
        source_label="Test spell",
        target_ref="goblin_1",
    )
    assert apply_condition(state, stunned).accepted
    use_deterministic_dice(session, die_roller=lambda _sides: 10)

    result = session.choose(action_id(session, "attack", "goblin_1"))

    attack = next(event for event in result.events if event.type == "attack_resolved")
    detail = attack.data["attack_roll_detail"]
    assert isinstance(detail, dict)
    assert detail["mode"] == "normal"
    assert detail["dice"] == [10]


def test_poisoned_is_exposed_in_the_public_creature_observation() -> None:
    session = _session()
    _apply_poisoned(session)

    observation = session.observe()
    assert observation.encounter is not None
    creature = next(
        creature
        for creature in observation.encounter.creatures
        if creature.creature_ref == "player"
    )

    assert "poisoned" in creature.effective_conditions
