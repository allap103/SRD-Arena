from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ...creatures import size_rank
from ...creatures.stat_block_actions import (
    ActionEffect,
    ConditionEffect,
    SizeRequirement,
)
from ...effects.results import EffectResult
from ...effects.application import condition_from_effect_with_origin
from ..models import EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState

HitEffectHandler = Callable[
    ["EncounterState", str, str, ActionEffect, EncounterProgress, str],
    None,
]


def apply_attack_hit_effects(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    effects: tuple[ActionEffect, ...],
    progress: EncounterProgress,
    origin_id: str | None = None,
) -> None:
    resolved_origin_id = origin_id or f"attack:{attacker_ref}:{target_ref}"
    for effect in effects:
        handler = _HIT_EFFECT_HANDLERS.get(type(effect))
        if handler is not None:
            handler(
                state,
                attacker_ref,
                target_ref,
                effect,
                progress,
                resolved_origin_id,
            )


def _apply_condition(
    state: EncounterState,
    attacker_ref: str,
    target_ref: str,
    effect: ActionEffect,
    progress: EncounterProgress,
    origin_id: str,
) -> None:
    if not isinstance(effect, ConditionEffect):
        return
    if effect.condition != "grappled":
        return
    attacker = state.creatures[attacker_ref].creature
    target = state.creatures[target_ref].creature
    maximum_size = next(
        (
            requirement.maximum
            for requirement in effect.requirements
            if isinstance(requirement, SizeRequirement)
        ),
        None,
    )
    if isinstance(maximum_size, str) and size_rank(target.size) > size_rank(
        maximum_size
    ):
        return
    already_grappled = attacker_ref in state._grappled_sources_for(target_ref)
    capacity = effect.source_capacity
    if (
        not already_grappled
        and isinstance(capacity, int)
        and len(state._grappling_targets_for(attacker_ref)) >= capacity
    ):
        return
    metadata = {
        "escape_dc": effect.escape_dc,
        "originating_action": "attack",
    }
    state._apply_grapple(
        condition_from_effect_with_origin(
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": attacker_ref,
                    "source_label": attacker.name,
                    "source_kind": "action",
                    "definition_id": "attack",
                    "metadata": metadata,
                },
            ),
            origin_id=origin_id,
        )
    )
    progress.messages.append(("system", f"{attacker.name} grapples {target.name}."))


_HIT_EFFECT_HANDLERS: dict[type[ActionEffect], HitEffectHandler] = {
    ConditionEffect: _apply_condition,
}
