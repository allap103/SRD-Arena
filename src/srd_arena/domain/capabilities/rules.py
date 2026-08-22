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
