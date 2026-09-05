"""Verify Hex through the canonical Warlock session boundary."""

from pathlib import Path
from typing import cast

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.rule_effects import AttackHitDamage, RollAdjustment
from srd_arena.domain.effects.runtime import EffectTag, OngoingEffectKind, Rounds
from srd_arena.domain.encounters.defeat import resolve_creature_defeat
from srd_arena.domain.encounters.effect_lifecycle.removal import remove_ongoing_effects
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.rule_queries.damage_riders import attack_hit_damage
from srd_arena.domain.encounters.rule_queries.rolls import roll_modifiers
from srd_arena.domain.encounters.state_combat import apply_combat_damage
from srd_arena.engine.queries import (
    ActionOption,
    DirectTargetOptionDetails,
    EffectRetargetOptionDetails,
    SpellOptionDetails,
)
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
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
        die_roller=lambda sides: 20 if sides == 20 else 3,
    )
    return session


def _hex_option(
    session: Session,
    target_ref: str,
    ability: str = "strength",
) -> ActionOption:
    return next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "spell"
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "hex"
        and option.details.target_ref == target_ref
        and option.details.selected_ability == ability
    )


def _cast_hex(
    session: Session,
    target_ref: str,
    ability: str = "strength",
) -> None:
    result = session._choose(_hex_option(session, target_ref, ability).id)
    assert any(event.type == "spell_cast" for event in result.events)


def test_hex_applies_a_sourced_concentration_curse_and_selected_check_penalty() -> None:
    session = _session()
    _cast_hex(session, "goblin_1", "strength")
    assert session.encounter_state is not None
    state = session.encounter_state

    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "hex"
    )
    assert effect.kind is OngoingEffectKind.CONCENTRATION
    assert effect.duration == Rounds(4_800)
    assert effect.tags == frozenset({EffectTag.CURSE})
    assert effect.target_refs == ("goblin_1",)
    assert effect.identity.source.applied_by_ref == "warlock"
    assert any(isinstance(rule, AttackHitDamage) for rule in effect.rule_effects)
    assert any(isinstance(rule, RollAdjustment) for rule in effect.rule_effects)
    assert (
        roll_modifiers(
            state,
            "goblin_1",
            "ability_check",
            ability="strength",
        ).mode
        == "disadvantage"
    )
    assert (
        roll_modifiers(
            state,
            "goblin_1",
            "ability_check",
            ability="dexterity",
        ).mode
        == "normal"
    )


def test_hex_adds_independently_typed_damage_to_the_casters_critical_hit() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_1"].creature.current_health = 100
    _cast_hex(session, "goblin_1")
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "hex"
    )

    attack = next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "attack"
        and isinstance(option.details, DirectTargetOptionDetails)
        and option.details.target_ref == "goblin_1"
    )
    result = session._choose(attack.id)
    if state.current_decision().kind == "d20_roll_modifier":
        decline = next(
            option
            for option in session._read().action_options
            if option.kind == "decline_d20_modifier"
        )
        result = session._choose(decline.id)
    event = next(event for event in result.events if event.type == "attack_resolved")
    detail = cast(dict[str, object], event.data["damage_roll_detail"])
    additional = cast(list[dict[str, object]], detail["additional_damage"])

    assert event.data["critical_hit"] is True
    assert additional == [
        {
            "dice": "2d6",
            "dice_values": [3, 3],
            "die_rolls": [[3], [3]],
            "dice_total": 6,
            "modifier": 0,
            "sourced_modifier": 0,
            "total": 6,
            "damage_type": "necrotic",
            "critical_hit": True,
            "provider_state_ids": [effect.identity.id],
        }
    ]


def test_hex_retargeting_appears_only_on_a_later_turn_and_moves_the_mark() -> None:
    session = _session()
    _cast_hex(session, "goblin_1")
    assert session.encounter_state is not None
    state = session.encounter_state
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "hex"
    )

    target = state.creatures["goblin_1"].creature
    apply_combat_damage(state, "goblin_1", target.get_health())
    resolve_creature_defeat(
        state,
        "goblin_1",
        defeated_by_ref="warlock",
        progress=EncounterProgress(),
    )
    assert not any(
        option.kind == "retarget_effect" for option in session._read().action_options
    )

    state.round.number += 1
    state.active_bonus_action_available = True
    retarget = next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "retarget_effect"
        and isinstance(option.details, EffectRetargetOptionDetails)
        and option.details.target_ref == "goblin_2"
    )
    observed_retarget = next(
        option
        for option in session.observe().scene.action_details
        if option.id == retarget.id
    )
    assert isinstance(retarget.details, EffectRetargetOptionDetails)
    assert retarget.details.effect_id == effect.identity.id
    assert observed_retarget.effect_id == effect.identity.id
    result = session._choose(retarget.id)

    assert [event.type for event in result.events][-1] == "effect_retargeted"
    assert effect.identity.id == state.ongoing_effects[0].identity.id
    assert state.ongoing_effects[0].target_refs == ("goblin_2",)
    assert state.active_bonus_action_available is False
    assert attack_hit_damage(state, "warlock", "goblin_1") == ()
    assert len(attack_hit_damage(state, "warlock", "goblin_2")) == 1


def test_remove_curse_finds_hex_without_ending_concentration_semantics() -> None:
    session = _session()
    _cast_hex(session, "goblin_1")
    assert session.encounter_state is not None
    state = session.encounter_state

    remove_ongoing_effects(
        state,
        EffectResult(
            "remove_effect",
            "goblin_1",
            data={"effect_kind": "curse"},
        ),
    )

    assert not any(
        effect.identity.source.definition_id == "hex"
        for effect in state.ongoing_effects
    )
