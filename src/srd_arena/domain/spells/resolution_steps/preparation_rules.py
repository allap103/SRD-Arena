"""Prepare saving-throw, condition, and lifecycle facts for spell resolution."""

from dataclasses import dataclass

from srd_arena.domain.capabilities import (
    AutomaticResolution,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityResolution,
    ConditionEffect,
    ConditionImmunityRequirement,
    CreatureTraitRequirement,
    CreatureTypeRequirement,
    DamageEffect,
    RelationshipRequirement,
    RepeatSave,
    SavingThrowResolution,
)

from ..definitions import SpellDamage


@dataclass(frozen=True)
class PreparedSpellRules:
    """Collect normalized save, condition, and lifecycle rules for one casting."""

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


def prepare_spell_rules(
    definition: CapabilityDefinition,
    resolution: CapabilityResolution,
    resolved_effects: tuple[CapabilityEffect, ...],
) -> PreparedSpellRules:
    """Normalize saving-throw requirements and ongoing lifecycle metadata.

    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget, Outcome,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome())
    ... )
    >>> rules = prepare_spell_rules(definition, definition.resolution, ())
    >>> (rules.save_ability, rules.conditions, rules.repeat_save)
    (None, (), None)
    """

    saving_throw = resolution if isinstance(resolution, SavingThrowResolution) else None
    conditions = tuple(
        effect.condition
        for effect in resolved_effects
        if isinstance(effect, ConditionEffect)
    )
    repeat_save = (
        next(
            (repeat for stage in saving_throw.failure for repeat in stage.repeat_saves),
            None,
        )
        if saving_throw is not None
        else None
    )
    repeat_effects = repeat_save.failure_effects if repeat_save is not None else ()
    return PreparedSpellRules(
        save_ability=saving_throw.ability if saving_throw is not None else None,
        half_damage_on_save=bool(
            saving_throw is not None and saving_throw.success_damage == "half"
        ),
        conditions=conditions,
        automatic_failure_creature_types=tuple(
            creature_type
            for requirement in (
                saving_throw.automatic_failure if saving_throw is not None else ()
            )
            if isinstance(requirement, CreatureTypeRequirement)
            for creature_type in requirement.creature_types
        ),
        automatic_success_condition_immunities=tuple(
            requirement.condition
            for requirement in (
                saving_throw.automatic_success if saving_throw is not None else ()
            )
            if isinstance(requirement, ConditionImmunityRequirement)
        ),
        automatic_success_traits=tuple(
            requirement.trait
            for requirement in (
                saving_throw.automatic_success if saving_throw is not None else ()
            )
            if isinstance(requirement, CreatureTraitRequirement)
        ),
        disadvantage_creature_types=tuple(
            creature_type
            for modifier in (
                saving_throw.save_modifiers if saving_throw is not None else ()
            )
            if modifier.mode == "disadvantage"
            for requirement in modifier.requirements
            if isinstance(requirement, CreatureTypeRequirement)
            for creature_type in requirement.creature_types
        ),
        expires_on_source_turn_end=any(
            isinstance(effect, ConditionEffect)
            and effect.duration is not None
            and effect.duration.kind == "end_of_turn"
            and effect.duration.creature == "source"
            for effect in resolved_effects
        ),
        repeat_save=repeat_save,
        repeat_failure_conditions=tuple(
            effect.condition
            for effect in repeat_effects
            if isinstance(effect, ConditionEffect)
        ),
        repeat_failure_damage=tuple(
            SpellDamage(effect.dice, effect.damage_type)
            for effect in repeat_effects
            if isinstance(effect, DamageEffect)
        ),
        end_events=tuple(
            (
                trigger.event,
                (
                    "source_team"
                    if any(
                        isinstance(requirement, RelationshipRequirement)
                        and requirement.relationship == "ally_of_source"
                        for requirement in trigger.requirements
                    )
                    else "any"
                ),
            )
            for trigger in definition.triggers
            if isinstance(trigger.resolution, AutomaticResolution)
            and trigger.resolution.outcome.end_capability
        ),
        damage_repeat_save_advantage=any(
            trigger.event == "target_damaged"
            and isinstance(trigger.resolution, SavingThrowResolution)
            and any(
                modifier.mode == "advantage"
                for modifier in trigger.resolution.save_modifiers
            )
            for trigger in definition.triggers
        ),
    )
