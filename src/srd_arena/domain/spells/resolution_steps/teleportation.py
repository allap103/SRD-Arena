"""Resolve immediate teleport effects after their destination was validated."""

from srd_arena.domain.capabilities import TeleportEffect, primary_effects
from srd_arena.domain.effects import EffectResult

from .context import SpellActionContext, SpellTargetContext


def build_spell_teleports(
    context: SpellActionContext,
    affected_targets: list[SpellTargetContext],
) -> list[EffectResult]:
    """Build encounter-neutral mutations for an affected teleport target."""

    teleport = next(
        (
            effect
            for effect in primary_effects(context.spell.definition)
            if isinstance(effect, TeleportEffect)
        ),
        None,
    )
    if teleport is None:
        return []
    destination = context.destination
    if destination is None:
        raise ValueError("A teleport effect requires a selected destination.")
    if len(affected_targets) != 1:
        raise ValueError(
            "One selected destination requires exactly one teleport target."
        )
    target = affected_targets[0]
    return [
        EffectResult(
            "teleport",
            target.target_ref,
            data={
                "x": destination.x,
                "y": destination.y,
                "distance_feet": teleport.distance_feet,
            },
        )
    ]
