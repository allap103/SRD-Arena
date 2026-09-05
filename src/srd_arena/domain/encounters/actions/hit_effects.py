"""Apply damage and secondary effects after an attack has hit."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import CapabilityEffect, ConditionEffect

from ..encounter_models.resolution import EncounterProgress
from .condition_effects import apply_sourced_condition_effect

if TYPE_CHECKING:
    from ..encounter import EncounterState

HitEffectHandler = Callable[
    ["EncounterState", str, str, CapabilityEffect, EncounterProgress, str],
    None,
]


def apply_attack_hit_effects(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    effects: tuple[CapabilityEffect, ...],
    progress: EncounterProgress,
    origin_id: str | None = None,
) -> None:
    """Apply an attack's damage and sourced conditions to its confirmed target.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock, patch
    >>> state = SimpleNamespace(
    ...     creatures={
    ...         "wolf": SimpleNamespace(creature=SimpleNamespace(name="Wolf")),
    ...         "hero": SimpleNamespace(
    ...             creature=SimpleNamespace(name="Hero", size="M")
    ...         ),
    ...     },
    ...     round=SimpleNamespace(number=1),
    ... )
    >>> progress = EncounterProgress()
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.condition_effects.apply_condition",
    ...     return_value=SimpleNamespace(accepted=True),
    ... ):
    ...     apply_attack_hit_effects(
    ...         state, attacker_ref="wolf", target_ref="hero",
    ...         effects=(ConditionEffect("prone"),), progress=progress,
    ...         origin_id="bite-1",
    ...     )
    >>> progress.messages
    [('system', 'Hero is prone.')]
    """

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
    effect: CapabilityEffect,
    progress: EncounterProgress,
    origin_id: str,
) -> None:
    if not isinstance(effect, ConditionEffect):
        return
    apply_sourced_condition_effect(
        state,
        source_ref=attacker_ref,
        target_ref=target_ref,
        effect=effect,
        progress=progress,
        origin_id=origin_id,
        definition_id="attack",
        originating_action="attack",
    )


_HIT_EFFECT_HANDLERS: dict[type[CapabilityEffect], HitEffectHandler] = {
    ConditionEffect: _apply_condition,
}
