"""Interpret an authored spell definition into a runtime resolution plan."""

from dataclasses import dataclass

from srd_arena.domain.capabilities import (
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityResolution,
    HealingEffect,
    RepeatSave,
    RollModifierEffect,
    TemporaryHitPointsEffect,
    capability_effects,
    primary_effects,
)
from srd_arena.domain.rolls.dice import DicePoolResult

from ..definitions import SpellDamage
from .context import SpellActionContext, SpellTargetContext
from .preparation_rolls import prepare_spell_rolls
from .preparation_rules import prepare_spell_rules


@dataclass(frozen=True)
class PreparedSpellResolution:
    """Cache normalized mechanics and shared rolls for one spell invocation."""

    definition: CapabilityDefinition
    resolution: CapabilityResolution
    definition_effects: tuple[CapabilityEffect, ...]
    targets: tuple[SpellTargetContext, ...]
    cast_level: int
    levels_above: int
    save_ability: str | None
    half_damage_on_save: bool
    conditions: tuple[str, ...]
    automatic_failure_creature_types: tuple[str, ...]
    automatic_success_condition_immunities: tuple[str, ...]
    automatic_success_traits: tuple[str, ...]
    disadvantage_creature_types: tuple[str, ...]
    expires_on_source_turn_end: bool
    repeat_save: RepeatSave | None
    repeat_failure_conditions: tuple[str, ...]
    repeat_failure_damage: tuple[SpellDamage, ...]
    end_events: tuple[tuple[str, str], ...]
    damage_repeat_save_advantage: bool
    healing_effects: tuple[HealingEffect, ...]
    temporary_hit_point_effects: tuple[TemporaryHitPointsEffect, ...]
    roll_modifier_effects: tuple[RollModifierEffect, ...]
    damage_definitions: tuple[SpellDamage, ...]
    shared_damage_rolls: tuple[tuple[SpellDamage, DicePoolResult], ...]
    shared_healing_rolls: tuple[
        tuple[HealingEffect, str | None, DicePoolResult | None], ...
    ]


def prepare_spell_resolution(context: SpellActionContext) -> PreparedSpellResolution:
    """Normalize spell rules and perform rolls shared by every resolved target.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget,
    ...     DamageEffect, Outcome,
    ... )
    >>> from ..definitions import Spell
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget('creature'),
    ...     AutomaticResolution(Outcome((DamageEffect('1d6', 0, 'fire'),))),
    ... )
    >>> spell = Spell('spark', 'Spark', 'TEST', 1, definition=definition)
    >>> context = SimpleNamespace(
    ...     spell=spell,
    ...     environment=SimpleNamespace(
    ...         roll_die=lambda sides: 4,
    ...         damage_roll_modifier=lambda: 0,
    ...     ),
    ...     cast_level=None,
    ...     creature=SimpleNamespace(attributes=SimpleNamespace(level=1)),
    ...     target='target', targets=(),
    ... )
    >>> prepare_spell_resolution(context).damage_definitions
    (SpellDamage(dice='1d6', damage_type='fire'),)
    """

    definition = context.spell.definition
    assert definition is not None

    definition_effects = capability_effects(definition)
    resolved_effects = primary_effects(definition)
    healing_effects = tuple(
        effect for effect in definition_effects if isinstance(effect, HealingEffect)
    )
    temporary_hit_point_effects = tuple(
        effect
        for effect in definition_effects
        if isinstance(effect, TemporaryHitPointsEffect)
    )
    roll_modifier_effects = tuple(
        effect
        for effect in definition_effects
        if isinstance(effect, RollModifierEffect)
    )
    rules = prepare_spell_rules(
        definition,
        definition.resolution,
        resolved_effects,
    )
    rolls = prepare_spell_rolls(
        context,
        definition,
        definition.resolution,
        resolved_effects,
        healing_effects,
    )

    return PreparedSpellResolution(
        definition=definition,
        resolution=definition.resolution,
        definition_effects=definition_effects,
        targets=context.targets or (context.target,),
        cast_level=rolls.cast_level,
        levels_above=rolls.levels_above,
        save_ability=rules.save_ability,
        half_damage_on_save=rules.half_damage_on_save,
        conditions=rules.conditions,
        automatic_failure_creature_types=rules.automatic_failure_creature_types,
        automatic_success_condition_immunities=(
            rules.automatic_success_condition_immunities
        ),
        automatic_success_traits=rules.automatic_success_traits,
        disadvantage_creature_types=rules.disadvantage_creature_types,
        expires_on_source_turn_end=rules.expires_on_source_turn_end,
        repeat_save=rules.repeat_save,
        repeat_failure_conditions=rules.repeat_failure_conditions,
        repeat_failure_damage=rules.repeat_failure_damage,
        end_events=rules.end_events,
        damage_repeat_save_advantage=rules.damage_repeat_save_advantage,
        healing_effects=healing_effects,
        temporary_hit_point_effects=temporary_hit_point_effects,
        roll_modifier_effects=roll_modifier_effects,
        damage_definitions=rolls.damage_definitions,
        shared_damage_rolls=rolls.shared_damage_rolls,
        shared_healing_rolls=rolls.shared_healing_rolls,
    )
