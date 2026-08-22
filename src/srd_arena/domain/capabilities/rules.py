"""Queries over provider-neutral capability definitions."""

from .definitions import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    SavingThrowResolution,
)
from .models import (
    CapabilityEffect,
    CapabilityRequirement,
    ConditionEffect,
    DamageEffect,
    RemoveEffect,
)


def capability_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return every effect reachable from a capability's primary resolution."""
    if definition is None:
        return ()
    resolution = definition.resolution
    if isinstance(resolution, AutomaticResolution):
        return resolution.outcome.effects
    if isinstance(resolution, AttackResolution):
        return (*resolution.hit.effects, *resolution.miss.effects)
    if isinstance(resolution, SavingThrowResolution):
        return (
            *(effect for stage in resolution.failure for effect in stage.effects),
            *resolution.success.effects,
            *resolution.always.effects,
        )
    return ()


def primary_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return effects applied when the primary resolution succeeds."""
    if definition is None:
        return ()
    resolution = definition.resolution
    if isinstance(resolution, AutomaticResolution):
        return resolution.outcome.effects
    if isinstance(resolution, AttackResolution):
        return resolution.hit.effects
    if isinstance(resolution, SavingThrowResolution):
        return tuple(effect for stage in resolution.failure for effect in stage.effects)
    return ()


def capability_geometry_mode(definition: CapabilityDefinition | None) -> str:
    """Classify a capability's targeting geometry for encounter presentation."""
    if definition is None:
        return "point_target"
    target = definition.target
    if target.kind == "self":
        return "self_only"
    if target.kind != "area":
        return "point_target"
    return "directional_area" if target.origin == "self" else "point_area"


def capability_area_size_feet(definition: CapabilityDefinition | None) -> int | None:
    """Return the primary authored area dimension."""
    if definition is None or definition.target.kind != "area":
        return None
    return definition.target.size_feet


def capability_target_requirements(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityRequirement, ...]:
    """Return the requirements imposed on selected targets."""
    return definition.target.requirements if definition is not None else ()


def capability_removal_effect(
    definition: CapabilityDefinition | None,
) -> RemoveEffect | None:
    """Return the primary removal effect, when one exists."""
    return next(
        (
            effect
            for effect in primary_effects(definition)
            if isinstance(effect, RemoveEffect)
        ),
        None,
    )


def capability_removable_conditions(
    definition: CapabilityDefinition | None,
) -> tuple[str, ...]:
    removal = capability_removal_effect(definition)
    return removal.conditions if removal is not None else ()


def capability_removable_effect_kinds(
    definition: CapabilityDefinition | None,
) -> tuple[str, ...]:
    removal = capability_removal_effect(definition)
    return removal.removable if removal is not None else ()


def capability_remove_effect_selection(
    definition: CapabilityDefinition | None,
) -> str | None:
    removal = capability_removal_effect(definition)
    return removal.selection if removal is not None else None


def capability_damage_dice(definition: CapabilityDefinition | None) -> str | None:
    """Return the first primary damage expression."""
    damage = next(
        (
            effect
            for effect in primary_effects(definition)
            if isinstance(effect, DamageEffect)
        ),
        None,
    )
    return damage.dice if damage is not None else None


def capability_damage_types(
    definition: CapabilityDefinition | None,
) -> tuple[str, ...]:
    """Return distinct damage types reachable from the primary resolution."""
    return tuple(
        dict.fromkeys(
            effect.damage_type
            for effect in capability_effects(definition)
            if isinstance(effect, DamageEffect)
        )
    )


def capability_inflicted_conditions(
    definition: CapabilityDefinition | None,
) -> tuple[str, ...]:
    """Return distinct conditions reachable from the primary resolution."""
    return tuple(
        dict.fromkeys(
            effect.condition
            for effect in capability_effects(definition)
            if isinstance(effect, ConditionEffect)
        )
    )


def capability_saving_throw_abilities(
    definition: CapabilityDefinition | None,
) -> tuple[str, ...]:
    """Return the ability used by a primary saving throw."""
    if definition is None or not isinstance(
        definition.resolution, SavingThrowResolution
    ):
        return ()
    return (definition.resolution.ability,)
