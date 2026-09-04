"""Verify Armor of Agathys through the canonical Warlock session boundary."""

from dataclasses import replace
from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.capabilities import AttackResolution
from srd_arena.domain.effects.rule_effects import AttackHitRetaliation
from srd_arena.domain.effects.runtime import (
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    OngoingEffectLifecycle,
    RuntimeStateIdentity,
)
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import DirectTargetOptionDetails, SpellOptionDetails
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    build_referenced_spell,
    player_first_initiative,
    use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session() -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 20 if sides == 20 else 1,
    )
    return session


def _cast_armor_of_agathys(session: Session) -> None:
    option = next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "spell"
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "armor_of_agathys"
        and option.details.resource_level == 3
    )
    result = session._choose(option.id)
    assert any(event.type == "spell_cast" for event in result.events)


def _make_goblin_active(session: Session) -> None:
    assert session.encounter_state is not None
    state = session.encounter_state
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "goblin_1"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("goblin_1")
    state.interrupts.decision_stack.clear()
    goblin = state.creatures["goblin_1"]
    goblin.creature.max_health_override = 50
    goblin.creature.current_health = 50
    goblin.position.x = state.creatures["warlock"].position.x + 1
    goblin.position.y = state.creatures["warlock"].position.y
    goblin.actions_remaining = 1
    goblin.action_used_this_turn = False


def _attack_warlock(session: Session, attack_type: str = "melee") -> EngineOutcome:
    option = next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "attack"
        and option.preferred_attack_type == attack_type
        and isinstance(option.details, DirectTargetOptionDetails)
        and option.details.target_ref == "warlock"
    )
    return session._choose(option.id)


def test_armor_of_agathys_grants_scaled_temporary_hit_points_and_rule_state() -> None:
    session = _session()

    _cast_armor_of_agathys(session)

    assert session.encounter_state is not None
    state = session.encounter_state
    warlock = state.creatures["warlock"].creature
    assert warlock.temporary_hit_points == 15
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "armor_of_agathys"
    )
    retaliation = next(
        rule for rule in effect.rule_effects if isinstance(rule, AttackHitRetaliation)
    )
    assert retaliation.damage == 15
    assert retaliation.damage_type == "cold"
    assert retaliation.attack_types == frozenset({"melee"})
    assert effect.lifecycle.ends_when_temporary_hit_points_depleted is True
    observation = session.observe().encounter
    assert observation is not None
    observed = observation.creature("warlock")
    assert observed.temporary_hit_points == 15


def test_melee_hit_takes_retaliation_while_temporary_hit_points_remain() -> None:
    session = _session()
    _cast_armor_of_agathys(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    _make_goblin_active(session)
    goblin = state.creatures["goblin_1"].creature
    initial_health = goblin.get_health()

    result = _attack_warlock(session)

    retaliation = next(
        event for event in result.events if event.type == "attack_hit_retaliation"
    )
    assert retaliation.data["source_definition_id"] == "armor_of_agathys"
    assert retaliation.data["requested_damage"] == 15
    assert retaliation.data["damage"] == 15
    assert retaliation.data["damage_type"] == "cold"
    assert goblin.get_health() == initial_health - 15
    assert any(
        effect.identity.source.definition_id == "armor_of_agathys"
        for effect in state.ongoing_effects
    )


def test_hit_that_depletes_last_temporary_hit_point_still_retaliates() -> None:
    session = _session()
    _cast_armor_of_agathys(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["warlock"].creature.temporary_hit_points = 1
    _make_goblin_active(session)
    goblin = state.creatures["goblin_1"].creature
    initial_health = goblin.get_health()

    result = _attack_warlock(session)

    assert any(event.type == "attack_hit_retaliation" for event in result.events)
    assert goblin.get_health() == initial_health - 15
    assert state.creatures["warlock"].creature.temporary_hit_points == 0
    assert not any(
        effect.identity.source.definition_id == "armor_of_agathys"
        for effect in state.ongoing_effects
    )


def test_ranged_hit_does_not_trigger_melee_retaliation() -> None:
    session = _session()
    _cast_armor_of_agathys(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    _make_goblin_active(session)
    goblin = state.creatures["goblin_1"].creature
    initial_health = goblin.get_health()

    result = _attack_warlock(session, "ranged")

    assert not any(event.type == "attack_hit_retaliation" for event in result.events)
    assert goblin.get_health() == initial_health
    assert any(
        effect.identity.source.definition_id == "armor_of_agathys"
        for effect in state.ongoing_effects
    )


def test_missed_melee_attack_does_not_trigger_retaliation() -> None:
    session = _session()
    _cast_armor_of_agathys(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    _make_goblin_active(session)
    goblin = state.creatures["goblin_1"].creature
    initial_health = goblin.get_health()
    use_deterministic_dice(session, die_roller=lambda _sides: 1)

    result = _attack_warlock(session)

    attack = next(event for event in result.events if event.type == "attack_resolved")
    assert attack.data["hit"] is False
    assert not any(event.type == "attack_hit_retaliation" for event in result.events)
    assert goblin.get_health() == initial_health


def test_melee_spell_attack_uses_the_same_retaliation_path() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    warlock = state.creatures["warlock"].creature
    goblin = state.creatures["goblin_1"].creature
    state.creatures["goblin_1"].position.x = state.creatures["warlock"].position.x + 1
    state.creatures["goblin_1"].position.y = state.creatures["warlock"].position.y
    goblin.temporary_hit_points = 5
    source = EffectSource(
        EffectSourceKind.SPELL,
        "test_frost_ward",
        applied_by_ref="goblin_1",
        origin_id="test-ward",
    )
    state.ongoing_effects.append(
        OngoingEffect(
            RuntimeStateIdentity("test-ward", source),
            ("goblin_1",),
            lifecycle=OngoingEffectLifecycle(
                ends_when_temporary_hit_points_depleted=True
            ),
            rule_effects=(AttackHitRetaliation(5, "cold", frozenset({"melee"}), True),),
        )
    )
    assert warlock.spellcasting is not None
    fire_bolt = build_referenced_spell(
        "Fire Bolt",
        "XPHB",
        load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )
    assert fire_bolt.definition is not None
    resolution = fire_bolt.definition.resolution
    assert isinstance(resolution, AttackResolution)
    melee_spell = replace(
        fire_bolt,
        id="test_melee_spell",
        name="Test Melee Spell",
        definition=replace(
            fire_bolt.definition,
            resolution=replace(resolution, modes=("melee",)),
            repetition=None,
        ),
    )
    warlock.spellcasting.learned_spells.append(melee_spell)
    initial_health = warlock.get_health()
    option = next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "spell"
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "test_melee_spell"
        and option.details.target_ref == "goblin_1"
    )

    result = session._choose(option.id)

    retaliation_events = [
        event for event in result.events if event.type == "attack_hit_retaliation"
    ]
    assert retaliation_events, [(event.type, event.data) for event in result.events]
    retaliation = retaliation_events[0]
    assert retaliation.data["source_definition_id"] == "test_frost_ward"
    assert retaliation.data["damage"] == 5
    assert warlock.get_health() == initial_health - 5
