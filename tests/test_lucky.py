"""Verify Lucky's resource pool and addressed D20 roll decisions."""

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.capabilities import CapabilityTarget, DamageEffect, OutcomeStage
from srd_arena.domain.creatures import RestType, SavingThrowActionDefinition
from srd_arena.domain.geometry import Position
from srd_arena.domain.spells.rules import SpellActionPayload
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    keep_alert_initiative,
    use_deterministic_dice,
)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session(
    d20_values: tuple[int, ...],
) -> tuple[Session, Iterator[int]]:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    rolls = iter(d20_values)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: next(rolls) if sides == 20 else 5,
    )
    return session, rolls


def _set_external(session: Session, creature_id: str) -> None:
    state = session.encounter_state
    assert state is not None
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == creature_id
    )
    participant.controller = "external"


def _spell_action_id(session: Session, spell_id: str, target_ref: str) -> str:
    state = session.encounter_state
    assert state is not None
    session._read()
    return next(
        action.id
        for action in state.available_actions()
        if action.kind == "spell"
        and isinstance(action.value, SpellActionPayload)
        and action.value.spell_id == spell_id
        and action.value.target_ref == target_ref
    )


def _use_lucky(session: Session) -> EngineOutcome:
    option = next(
        option
        for option in session._read().action_options
        if option.kind == "use_lucky"
    )
    return session._choose(option.id)


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    return cast(Sequence[object], value)


def test_lucky_uses_proficiency_bonus_and_recovers_on_a_long_rest() -> None:
    """Give the level-five Warlock three Luck Points and restore them by resting."""

    session, _rolls = _session(())
    state = session.encounter_state
    assert state is not None
    warlock = state.creatures["warlock"].creature

    assert warlock.combat_profile.feature_uses_max["lucky"] == 3
    assert warlock.feature_uses_remaining["lucky"] == 3
    warlock.spend_feature_use("lucky")

    recoveries = warlock.recover_resources(RestType.LONG)

    assert warlock.feature_uses_remaining["lucky"] == 3
    assert any(recovery.resource_id == "feature:lucky" for recovery in recoveries)


def test_lucky_advantage_is_addressed_to_one_eldritch_blast_beam() -> None:
    """Apply one Luck Point to the first beam without modifying the second."""

    session, _rolls = _session((4, 18, 3))
    state = session.encounter_state
    assert state is not None
    state.turn.index = state.initiative_order.index("warlock")
    state.creatures["warlock"].creature.feature_uses_remaining["lucky"] = 1

    session._choose(_spell_action_id(session, "eldritch_blast", "ogre_target"))
    add_second = next(
        option
        for option in session._read().action_options
        if option.kind == "toggle_spell_target"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
        and option.id.endswith("-add")
    )
    session._choose(add_second.id)
    confirm = next(
        option
        for option in session._read().action_options
        if option.kind == "confirm_spell_targets"
    )
    session._choose(confirm.id)

    assert state.current_decision().kind == "d20_roll_modifier"
    context = session.observe_player("heroes").decision_context
    assert context is not None
    assert context.trigger == "d20_roll_modifier"
    assert context.roll_kind == "attack_roll"
    assert context.offered_roll_mode == "advantage"
    assert context.actor_ref == "warlock"
    assert context.target_ref == "ogre_target"
    resolved = _use_lucky(session)
    events = list(resolved.events)
    while state.current_decision().kind == "forced_movement":
        decline_push = next(
            option
            for option in session._read().action_options
            if option.kind == "forced_movement_choice"
            and option.label.startswith("Do not use")
        )
        events.extend(session._choose(decline_push.id).events)

    projectile_events = [
        event for event in events if event.type == "spell_projectile_resolved"
    ]
    first = _mapping(projectile_events[0].data["attack_roll_detail"])
    second = _mapping(projectile_events[1].data["attack_roll_detail"])
    assert first["dice"] == [4, 18]
    assert first["mode"] == "advantage"
    assert first["hit"] is True
    assert second["dice"] == [3]
    assert second["mode"] == "normal"
    assert second["hit"] is False
    assert state.creatures["warlock"].creature.feature_uses_remaining["lucky"] == 0


def test_lucky_can_impose_disadvantage_on_an_incoming_attack() -> None:
    """Let the target spend Luck before one ordinary enemy attack resolves."""

    session, _rolls = _session((18, 2))
    state = session.encounter_state
    assert state is not None
    _set_external(session, "goblin_1")
    state.turn.index = state.initiative_order.index("goblin_1")
    state.creatures["goblin_1"].position = Position(3, 3)
    state.creatures["warlock"].position = Position(4, 3)
    session._read()
    attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "warlock"
    )

    session._choose(attack.id)

    assert state.current_decision().kind == "d20_roll_modifier"
    assert state.current_decision().creature_ref == "warlock"
    resolved = _use_lucky(session)
    event = next(event for event in resolved.events if event.type == "attack_resolved")
    detail = _mapping(event.data["attack_roll_detail"])
    assert detail["dice"] == [18, 2]
    assert detail["mode"] == "disadvantage"
    assert event.data["hit"] is False


def test_lucky_can_grant_advantage_on_a_spell_saving_throw() -> None:
    """Offer the saving creature Lucky before resolving Mind Sliver."""

    session, _rolls = _session((2, 18))
    state = session.encounter_state
    assert state is not None
    _set_external(session, "goblin_1")
    state.turn.index = state.initiative_order.index("warlock")
    warlock = state.creatures["warlock"].creature
    goblin = state.creatures["goblin_1"].creature
    goblin.character_profile = warlock.character_profile
    goblin.feature_uses_remaining["lucky"] = 3

    session._choose(_spell_action_id(session, "mind_sliver", "goblin_1"))

    assert state.current_decision().kind == "d20_roll_modifier"
    assert state.current_decision().creature_ref == "goblin_1"
    resolved = _use_lucky(session)
    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    save = _mapping(_sequence(spell_event.data["save_details"])[0])
    assert save["dice"] == [2, 18]
    assert save["mode"] == "advantage"
    assert save["success"] is True
    assert goblin.feature_uses_remaining["lucky"] == 2


def test_lucky_can_grant_advantage_on_a_stat_block_saving_throw() -> None:
    """Route monster-authored saves through the same optional D20 boundary."""

    session, _rolls = _session((4, 17))
    state = session.encounter_state
    assert state is not None
    _set_external(session, "goblin_1")
    state.turn.index = state.initiative_order.index("goblin_1")
    state.creatures["goblin_1"].position = Position(3, 3)
    state.creatures["warlock"].position = Position(4, 3)
    goblin = state.creatures["goblin_1"].creature
    goblin.stat_block_actions["Test Roar"] = SavingThrowActionDefinition(
        name="Test Roar",
        target=CapabilityTarget("creature", range_feet=30),
        ability="wis",
        dc=30,
        failure=(OutcomeStage((DamageEffect("1d6", 0, "psychic"),)),),
        success=(),
        success_damage="none",
        always=(),
    )
    session._read()
    candidates = state.available_actions()
    matches = [
        action
        for action in candidates
        if action.kind == "stat_block"
        and action.preferred_attack_name == "Test Roar"
        and action.value == "warlock"
    ]
    assert matches, [
        (action.kind, action.preferred_attack_name, action.value)
        for action in candidates
    ]
    roar = matches[0]

    session._choose(roar.id)

    assert state.current_decision().kind == "d20_roll_modifier"
    assert state.current_decision().creature_ref == "warlock"
    resolved = _use_lucky(session)
    event = next(
        event for event in resolved.events if event.type == "stat_block_action_resolved"
    )
    outcome = _mapping(_sequence(event.data["outcomes"])[0])
    assert outcome["save_dice"] == [4, 17]
    assert outcome["save_mode"] == "advantage"
