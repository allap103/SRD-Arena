"""Apply damage and secondary effects after an attack has hit."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import (
    CapabilityEffect,
    ConditionEffect,
    SizeRequirement,
)
from srd_arena.domain.creatures import size_rank
from srd_arena.domain.effects.application import condition_from_effect_with_origin
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.effects.runtime import (
    EffectDuration,
    EffectSourceKind,
    Indefinite,
    UntilTurnEnd,
    UntilTurnStart,
)

from ..condition_state import apply_condition
from ..encounter_models.resolution import EncounterProgress
from ..grappling_state import (
    apply_grapple,
    grappled_sources_for,
    grappling_targets_for,
)

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
    ...         "hero": SimpleNamespace(creature=SimpleNamespace(name="Hero")),
    ...     },
    ...     round=SimpleNamespace(number=1),
    ... )
    >>> progress = EncounterProgress()
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.hit_effects.apply_condition",
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
    attacker = state.creatures[attacker_ref].creature
    target = state.creatures[target_ref].creature
    if effect.condition != "grappled":
        duration = _condition_duration(
            state,
            attacker_ref,
            target_ref,
            effect,
        )
        result = apply_condition(
            state,
            build_applied_condition(
                condition=Condition(effect.condition),
                source_ref=attacker_ref,
                source_label=attacker.name,
                target_ref=target_ref,
                source_kind=EffectSourceKind.ACTION,
                definition_id="attack",
                origin_id=origin_id,
                duration=duration,
            ),
        )
        if result.accepted:
            progress.messages.append(
                ("system", f"{target.name} is {effect.condition}.")
            )
        return
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
    already_grappled = attacker_ref in grappled_sources_for(state, target_ref)
    capacity = effect.source_capacity
    if (
        not already_grappled
        and isinstance(capacity, int)
        and len(grappling_targets_for(state, attacker_ref)) >= capacity
    ):
        return
    metadata = {
        "escape_dc": effect.escape_dc,
        "originating_action": "attack",
    }
    apply_grapple(
        state,
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
        ),
    )
    progress.messages.append(("system", f"{attacker.name} grapples {target.name}."))


def _condition_duration(
    state: EncounterState,
    attacker_ref: str,
    target_ref: str,
    effect: ConditionEffect,
) -> EffectDuration:
    duration = effect.duration
    if duration is None:
        return Indefinite()
    creature_ref = attacker_ref if duration.creature == "source" else target_ref
    round_number = state.round.number + duration.turn_offset
    if duration.kind == "start_of_turn":
        return UntilTurnStart(creature_ref, round_number)
    if duration.kind == "end_of_turn":
        return UntilTurnEnd(creature_ref, round_number)
    return Indefinite()


_HIT_EFFECT_HANDLERS: dict[type[CapabilityEffect], HitEffectHandler] = {
    ConditionEffect: _apply_condition,
}
