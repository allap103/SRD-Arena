"""Queries over provider-neutral capability definitions."""

from .definitions import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    SavingThrowResolution,
)
from .models import CapabilityEffect


def capability_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return every effect reachable from a capability's primary resolution.

    >>> from .definitions import AutomaticResolution, Outcome
    >>> from .models import CapabilityTarget, DamageEffect
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


def primary_effects(
    definition: CapabilityDefinition | None,
) -> tuple[CapabilityEffect, ...]:
    """Return effects applied when the primary resolution succeeds.

    For attacks, miss-only effects are deliberately excluded.

    >>> from .definitions import AttackResolution, FixedAttackBonus, Outcome
    >>> from .models import CapabilityTarget, DamageEffect
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
