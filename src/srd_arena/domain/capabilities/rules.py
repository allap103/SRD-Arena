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


def capability_area_shape(definition: CapabilityDefinition | None) -> str | None:
    """Return the authored area shape, when the capability targets an area."""
    if definition is None or definition.target.kind != "area":
        return None
    return definition.target.shape


def capability_chooses_area_targets(definition: CapabilityDefinition | None) -> bool:
    """Return whether creatures inside an area are selected explicitly."""
    return bool(
        definition is not None
        and definition.target.kind == "area"
        and definition.target.occupants == "chosen"
    )


def capability_target_disposition(
    definition: CapabilityDefinition | None,
) -> str | None:
    """Return the permitted creature disposition for a targeted capability."""
    if definition is not None and definition.target.kind == "creature":
        return definition.target.disposition
    return None


def capability_repeats_target_allocations(
    definition: CapabilityDefinition | None,
) -> bool:
    """Return whether repeated uses may be allocated to the same target."""
    return bool(
        definition is not None
        and definition.repetition is not None
        and definition.repetition.allocation in {"same_target", "same_or_different"}
    )


def capability_requires_full_target_count(
    definition: CapabilityDefinition | None,
) -> bool:
    """Return whether the authored repetition requires a complete allocation."""
    return bool(definition is not None and definition.repetition is not None)


def capability_supports_resource_scaling(
    definition: CapabilityDefinition | None,
) -> bool:
    """Return whether spending a higher resource tier changes the capability."""
    return bool(
        definition is not None
        and any(
            scaling.basis == "resource_level" and scaling.per_level
            for scaling in definition.scaling
        )
    )


def capability_max_targets(
    definition: CapabilityDefinition | None,
    *,
    base_resource_level: int = 0,
    resource_level: int | None = None,
    actor_level: int | None = None,
) -> int:
    """Resolve a capability's target count after actor and resource scaling."""
    if definition is None:
        return 1
    target_maximum = definition.target.count.maximum
    maximum = target_maximum if isinstance(target_maximum, int) else 1
    if definition.repetition is not None and isinstance(
        definition.repetition.count, int
    ):
        maximum = definition.repetition.count
    if actor_level is not None:
        thresholds = sorted(
            (
                threshold
                for scaling in definition.scaling
                if scaling.basis == "actor_level"
                for threshold in scaling.thresholds
                if threshold.minimum_level <= actor_level
                and any(
                    increment.kind in {"target_count", "projectile_count"}
                    and isinstance(increment.amount, int)
                    for increment in threshold.increments
                )
            ),
            key=lambda threshold: threshold.minimum_level,
        )
        if thresholds:
            maximum = next(
                increment.amount
                for increment in thresholds[-1].increments
                if increment.kind in {"target_count", "projectile_count"}
                and isinstance(increment.amount, int)
            )
    resolved_resource_level = (
        resource_level if resource_level is not None else base_resource_level
    )
    levels_above = max(0, resolved_resource_level - base_resource_level)
    per_level_increment = sum(
        increment.amount
        for scaling in definition.scaling
        if scaling.basis == "resource_level"
        for increment in scaling.per_level
        if increment.kind in {"target_count", "projectile_count"}
        and isinstance(increment.amount, int)
    )
    return maximum + levels_above * per_level_increment


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
