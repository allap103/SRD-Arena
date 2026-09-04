"""Queries over provider-neutral capability definitions."""

from .definitions import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    SavingThrowResolution,
)
from .effects import AttackHitDamageEffect, CapabilityEffect, DamageEffect
from .resolutions import CapabilityResolution


def capability_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return every effect reachable from a capability's primary resolution.

    >>> from .definitions import AutomaticResolution, Outcome
    >>> from .effects import DamageEffect
    >>> from .targeting import CapabilityTarget
    >>> damage = DamageEffect("1d6", 0, "fire")
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget(kind="self"),
    ...     AutomaticResolution(Outcome((damage,))),
    ... )
    >>> capability_effects(definition) == (damage,)
    True
    """
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


def all_capability_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return effects from primary, repeated, triggered, and follow-up resolution.

    >>> from .definitions import CapabilityTrigger, Outcome
    >>> from .effects import DamageEffect
    >>> from .targeting import CapabilityTarget
    >>> delayed = DamageEffect("1d6", 0, "fire")
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget(kind="creature"),
    ...     AutomaticResolution(Outcome()),
    ...     triggers=(CapabilityTrigger(
    ...         "turn_end", AutomaticResolution(Outcome((delayed,)))
    ...     ),),
    ... )
    >>> all_capability_effects(definition) == (delayed,)
    True
    """

    if definition is None:
        return ()
    return (
        *_resolution_effects(definition.resolution),
        *(
            effect
            for trigger in definition.triggers
            for effect in _resolution_effects(trigger.resolution)
        ),
        *(
            effect
            for follow_up in definition.follow_ups
            for effect in _resolution_effects(follow_up.resolution)
        ),
    )


def capability_can_damage(definition: CapabilityDefinition | None) -> bool:
    """Return whether any executable path in a capability can deal damage.

    >>> from .definitions import Outcome
    >>> from .targeting import CapabilityTarget
    >>> damage = DamageEffect("1d4", 0, "force")
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget(kind="creature"),
    ...     AutomaticResolution(Outcome((damage,))),
    ... )
    >>> capability_can_damage(definition)
    True
    >>> capability_can_damage(None)
    False
    """

    return any(
        isinstance(effect, (DamageEffect, AttackHitDamageEffect))
        for effect in all_capability_effects(definition)
    )


def _resolution_effects(
    resolution: CapabilityResolution,
) -> tuple[CapabilityEffect, ...]:
    """Return immediate and repeat-save effects reachable from a resolution."""

    if isinstance(resolution, AutomaticResolution):
        return resolution.outcome.effects
    if isinstance(resolution, AttackResolution):
        return (*resolution.hit.effects, *resolution.miss.effects)
    if isinstance(resolution, SavingThrowResolution):
        return (
            *(effect for stage in resolution.failure for effect in stage.effects),
            *(
                effect
                for stage in resolution.failure
                for repeat in stage.repeat_saves
                for effect in repeat.failure_effects
            ),
            *resolution.success.effects,
            *resolution.always.effects,
        )
    return ()


def primary_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return effects applied when the primary resolution succeeds.

    For attacks, miss-only effects are deliberately excluded.

    >>> from .definitions import AttackResolution, FixedAttackBonus, Outcome
    >>> from .effects import DamageEffect
    >>> from .targeting import CapabilityTarget
    >>> hit = DamageEffect("1d8", 2, "slashing")
    >>> miss = DamageEffect("1d4", 0, "force")
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget(kind="creature"),
    ...     AttackResolution(
    ...         ("melee",), FixedAttackBonus(5), Outcome((hit,)), Outcome((miss,))
    ...     ),
    ... )
    >>> primary_effects(definition) == (hit,)
    True
    """
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
