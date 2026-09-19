"""Detach authored spell mechanics and cast-level quantities without rolling dice."""

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from srd_arena.domain.capabilities import (
    AttackHitRetaliationEffect,
    DamageEffect,
    HealingEffect,
    HitPointMaximumModifierEffect,
    TemporaryHitPointsEffect,
)
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.custom.slow import SLOW_RULE_EFFECTS
from srd_arena.domain.spells.custom.stinking_cloud import (
    STINKING_CLOUD_OBSCURES_VISION,
    stinking_cloud_save,
)
from srd_arena.domain.spells.properties import spell_duration_rounds
from srd_arena.domain.spells.resolution_steps.scaling import (
    actor_level_damage_dice,
    resource_dice_increment,
    resource_duration_rounds,
    resource_int_increment,
    scale_dice,
)

from .values import EngineValue, freeze_mapping


def observe_spell_mechanics(
    spell: Spell,
    cast_level: int,
    *,
    caster_level: int,
    casting_modifier: int,
    casting_save_dc: int,
) -> Mapping[str, EngineValue]:
    """Expose definition branches, triggers, durations and custom rule supplements.

    These are intrinsic known mechanics, not a target-specific outcome forecast.
    Authored fields are preserved; cast_dice/cast_value add resource-level scaling.
    Python resolvers remain explicitly identified rather than claimed declarative.
    """

    def describe(value: object) -> EngineValue:
        """Convert definition values to immutable, tagged observation records."""
        if isinstance(value, Enum):
            return describe(value.value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (tuple, list)):
            return tuple(describe(v) for v in value)
        if isinstance(value, (frozenset, set)):
            return tuple(describe(v) for v in sorted(value, key=str))
        if is_dataclass(value) and not isinstance(value, type):
            data = {f.name: describe(getattr(value, f.name)) for f in fields(value)}
            data["type"] = re.sub(r"(?<!^)(?=[A-Z])", "_", type(value).__name__).lower()
            data.update(_cast_quantities(caster_level, spell, cast_level, value))
            return freeze_mapping(data)
        raise TypeError(f"Unsupported spell mechanics value: {type(value).__name__}")

    custom: dict[str, EngineValue] = {}
    if spell.resolver_id == "stinking_cloud":
        custom = {
            "persistent_area": True,
            "obscures_vision": STINKING_CLOUD_OBSCURES_VISION,
            "turn_start_save": describe(stinking_cloud_save(casting_save_dc)),
        }
    elif spell.resolver_id == "slow":
        custom = {"rule_effects": describe(SLOW_RULE_EFFECTS)}
    duration_rounds = (
        resource_duration_rounds(spell.definition, cast_level)
        if spell.definition is not None
        else None
    )
    if duration_rounds is None:
        duration_rounds = spell_duration_rounds(spell)
    return freeze_mapping(
        {
            "schema_id": "spell-mechanics-v1",
            "implementation": "custom"
            if spell.resolver_id
            else "declarative"
            if spell.definition
            else "unimplemented",
            "custom_resolver_id": spell.resolver_id,
            "definition": describe(spell.definition),
            "durations": describe(spell.durations),
            "duration_rounds": duration_rounds,
            "components": describe(spell.components.required),
            "target_requirements": describe(spell.target_requirements),
            "recast_ends_previous": spell.recast_ends_previous,
            "removable_conditions": spell.removable_conditions,
            "removable_effect_kinds": spell.removable_effect_kinds,
            "custom": custom,
            "caster_level": caster_level,
            "casting_modifier": casting_modifier,
        }
    )


def _cast_quantities(
    caster_level: int,
    spell: Spell,
    cast_level: int,
    effect: object,
) -> dict[str, EngineValue]:
    """Use runtime scaling helpers for individual authored effect quantities.

    Damage is per hit/target before defenses and contextual feature modifiers.
    Repetition and selection remain explicit in the surrounding definition.
    """
    definition = spell.definition
    if definition is None:
        return {}
    levels_above = max(0, cast_level - spell.level)
    if isinstance(effect, DamageEffect):
        dice = actor_level_damage_dice(definition, caster_level) or effect.dice
        return {
            "cast_dice": scale_dice(
                dice,
                resource_dice_increment(definition, "damage_dice", effect.damage_type),
                levels_above,
            )
        }
    if isinstance(effect, HealingEffect):
        return {
            "cast_dice": scale_dice(
                effect.dice,
                resource_dice_increment(definition, "healing_dice"),
                levels_above,
            ),
            "cast_bonus": effect.bonus
            + resource_int_increment(definition, "healing_bonus") * levels_above,
        }
    for effect_type, kind in (
        (TemporaryHitPointsEffect, "temporary_hit_points"),
        (AttackHitRetaliationEffect, "attack_hit_retaliation"),
        (HitPointMaximumModifierEffect, "hit_point_maximum"),
    ):
        if isinstance(effect, effect_type):
            return {
                "cast_value": effect.value
                + resource_int_increment(definition, kind) * levels_above
            }
    return {}
