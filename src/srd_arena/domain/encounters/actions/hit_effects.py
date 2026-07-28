from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ...creatures import size_rank
from ...creatures.stat_block_actions import ActionEffect
from ...effects.results import EffectResult
from ..models import EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState

HitEffectHandler = Callable[
    ["EncounterState", str, str, ActionEffect, EncounterProgress],
    None,
]


def apply_attack_hit_effects(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    effects: tuple[ActionEffect, ...],
    progress: EncounterProgress,
) -> None:
    for effect in effects:
        handler = _HIT_EFFECT_HANDLERS.get(effect.kind)
        if handler is not None:
            handler(state, attacker_ref, target_ref, effect, progress)


def _apply_condition(
    state: EncounterState,
    attacker_ref: str,
    target_ref: str,
    effect: ActionEffect,
    progress: EncounterProgress,
) -> None:
    if effect.parameters.get("condition") != "grappled":
        return
    attacker = state.creatures[attacker_ref].creature
    target = state.creatures[target_ref].creature
    requirements = effect.parameters.get("requirements", [])
    maximum_size = next(
        (
            requirement.get("maximum")
            for requirement in requirements
            if isinstance(requirement, dict)
            and requirement.get("type") == "size"
        ),
        None,
    )
    if (
        isinstance(maximum_size, str)
        and size_rank(target.size) > size_rank(maximum_size)
    ):
        return
    already_grappled = attacker_ref in state._grappled_sources_for(target_ref)
    capacity = effect.parameters.get("source_capacity")
    if (
        not already_grappled
        and isinstance(capacity, int)
        and len(state._grappling_targets_for(attacker_ref)) >= capacity
    ):
        return
    metadata = {
        "escape_dc": effect.parameters.get("escape_dc"),
        "originating_action": "attack",
    }
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": attacker_ref,
                    "source_label": attacker.name,
                    "metadata": metadata,
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref=attacker_ref,
                data={
                    "condition": "grappling",
                    "source_ref": target_ref,
                    "source_label": target.name,
                    "metadata": metadata,
                },
            ),
        ]
    )
    progress.messages.append(
        ("system", f"{attacker.name} grapples {target.name}.")
    )


_HIT_EFFECT_HANDLERS: dict[str, HitEffectHandler] = {
    "condition": _apply_condition,
}
