"""Prepare spell scaling and dice pools shared across resolved targets."""

from dataclasses import dataclass

from ...capabilities import (
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityResolution,
    DamageEffect,
    HealingEffect,
    SavingThrowResolution,
)
from ...rolls.dice import DicePoolResult, resolve_dice
from ..definitions import SpellDamage
from .context import SpellActionContext
from .details import roll_optional_dice
from .scaling import (
    actor_level_damage_dice,
    parse_damage_dice,
    resource_dice_increment,
    scale_dice,
)


@dataclass(frozen=True)
class PreparedSpellRolls:
    """Collect cast-level scaling and dice pools shared by every target."""

    cast_level: int
    levels_above: int
    damage_definitions: tuple[SpellDamage, ...]
    shared_damage_rolls: tuple[tuple[SpellDamage, DicePoolResult], ...]
    shared_healing_rolls: tuple[
        tuple[HealingEffect, str | None, DicePoolResult | None], ...
    ]


def prepare_spell_rolls(
    context: SpellActionContext,
    definition: CapabilityDefinition,
    resolution: CapabilityResolution,
    resolved_effects: tuple[CapabilityEffect, ...],
    healing_effects: tuple[HealingEffect, ...],
) -> PreparedSpellRolls:
    """Scale spell outcomes and perform rolls intentionally shared by targets.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget,
    ...     DamageEffect, Outcome,
    ... )
    >>> from ..definitions import Spell
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"),
    ...     AutomaticResolution(Outcome((DamageEffect("1d6", 0, "fire"),))),
    ... )
    >>> context = SimpleNamespace(
    ...     spell=Spell("spark", "Spark", "TEST", 1, definition=definition),
    ...     cast_level=1,
    ...     creature=SimpleNamespace(attributes=SimpleNamespace(level=1)),
    ...     environment=SimpleNamespace(
    ...         roll_die=lambda sides: 4,
    ...         damage_roll_modifier=lambda: 0,
    ...     ),
    ... )
    >>> prepare_spell_rolls(
    ...     context, definition, definition.resolution,
    ...     definition.resolution.outcome.effects, (),
    ... ).damage_definitions
    (SpellDamage(dice='1d6', damage_type='fire'),)
    """

    cast_level = (
        context.cast_level if context.cast_level is not None else context.spell.level
    )
    levels_above = cast_level - context.spell.level
    damage_definitions = _scaled_damage_definitions(
        definition,
        resolved_effects,
        caster_level=context.creature.attributes.level,
        levels_above=levels_above,
    )
    shared_damage_rolls = (
        tuple(
            (
                damage,
                resolve_dice(
                    *parse_damage_dice(damage.dice),
                    modifier=context.environment.damage_roll_modifier(),
                    roller=context.environment.roll_die,
                ),
            )
            for damage in damage_definitions
        )
        if isinstance(resolution, SavingThrowResolution)
        else ()
    )
    shared_healing_rolls = tuple(
        (
            healing,
            dice,
            roll_optional_dice(dice, context.environment.roll_die),
        )
        for healing in healing_effects
        if healing.pool is None
        for dice in (
            scale_dice(
                healing.dice,
                resource_dice_increment(definition, "healing_dice"),
                levels_above,
            ),
        )
    )
    return PreparedSpellRolls(
        cast_level=cast_level,
        levels_above=levels_above,
        damage_definitions=damage_definitions,
        shared_damage_rolls=shared_damage_rolls,
        shared_healing_rolls=shared_healing_rolls,
    )


def _scaled_damage_definitions(
    definition: CapabilityDefinition,
    resolved_effects: tuple[CapabilityEffect, ...],
    *,
    caster_level: int,
    levels_above: int,
) -> tuple[SpellDamage, ...]:
    """Return damage definitions after actor- and slot-level scaling."""

    damage_definitions = tuple(
        SpellDamage(effect.dice, effect.damage_type)
        for effect in resolved_effects
        if isinstance(effect, DamageEffect)
    )
    actor_damage_dice = actor_level_damage_dice(definition, caster_level)
    if actor_damage_dice is not None:
        damage_definitions = tuple(
            SpellDamage(actor_damage_dice, damage.damage_type)
            for damage in damage_definitions
        )
    if levels_above <= 0:
        return damage_definitions

    scaled: list[SpellDamage] = []
    for damage in damage_definitions:
        increment = resource_dice_increment(
            definition,
            "damage_dice",
            damage.damage_type,
        )
        if increment is None:
            scaled.append(damage)
            continue
        increment_count, increment_sides = parse_damage_dice(increment)
        count, sides = parse_damage_dice(damage.dice)
        if sides != increment_sides:
            raise ValueError("Slot damage scaling must use the base damage die.")
        scaled.append(
            SpellDamage(
                f"{count + increment_count * levels_above}d{sides}",
                damage.damage_type,
            )
        )
    return tuple(scaled)
