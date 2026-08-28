"""Remove ongoing effects and undo the runtime modifiers they installed."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...effects.results import EffectResult
from ...effects.rule_effects import MaximumHitPointAdjustment
from ...effects.runtime import OngoingEffect
from ..attack_economy import reconcile_remaining_attacks
from ..rule_queries.health import effective_maximum_health
from .movement import reconcile_remaining_movement

if TYPE_CHECKING:
    from ..encounter import EncounterState


def remove_ongoing_effects(state: EncounterState, result: EffectResult) -> None:
    """Remove matching effects from one target according to an effect result.

    By default only the first matching occurrence is removed; authored effects
    can explicitly request all matches.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> first = SimpleNamespace(
    ...     target_refs=("hero",),
    ...     identity=SimpleNamespace(id="bless-1"),
    ...     kind=SimpleNamespace(value="spell"),
    ... )
    >>> second = SimpleNamespace(
    ...     target_refs=("hero",),
    ...     identity=SimpleNamespace(id="bless-2"),
    ...     kind=SimpleNamespace(value="spell"),
    ... )
    >>> state = SimpleNamespace(ongoing_effects=[first, second])
    >>> result = EffectResult("remove_effect", "hero", data={"effect_kind": "spell"})
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.removal."
    ...     "_remove_effect_target"
    ... ) as remove:
    ...     remove_ongoing_effects(state, result)
    >>> remove.call_args.args[1] is first
    True
    """

    effect_id = result.data.get("effect_id")
    effect_kind = result.data.get("effect_kind")
    parameter = result.data.get("parameter")
    remove_all = bool(result.data.get("all", False))
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if result.target_ref in effect.target_refs
        and (not isinstance(effect_id, str) or effect.identity.id == effect_id)
        and (not isinstance(effect_kind, str) or effect.kind.value == effect_kind)
        and (
            parameter != "negative_maximum_hit_points"
            or any(
                isinstance(rule_effect, MaximumHitPointAdjustment)
                and rule_effect.value < 0
                for rule_effect in effect.rule_effects
            )
        )
    )
    for effect in matching if remove_all else matching[:1]:
        _remove_effect_target(state, effect, result.target_ref)


def _remove_effect_tree(state: EncounterState, effect: OngoingEffect) -> None:
    """Remove an ongoing effect, every target modifier, and child condition."""

    origin_id = effect.identity.source.origin_id
    previous_maximums = _maximums_before_removal(state, effect, effect.target_refs)
    state.ongoing_effects = [
        existing
        for existing in state.ongoing_effects
        if existing.identity.id != effect.identity.id
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.identity.source.origin_id != origin_id
    ]
    _adjust_current_health_after_removal(state, previous_maximums)
    reconcile_remaining_attacks(state, effect.target_refs)
    reconcile_remaining_movement(state, effect.target_refs)


def _remove_effect_target(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    """Detach one target while retaining a multi-target effect for the rest."""

    previous_maximums = _maximums_before_removal(state, effect, (target_ref,))
    remaining_targets = tuple(
        existing for existing in effect.target_refs if existing != target_ref
    )
    state.conditions = [
        condition
        for condition in state.conditions
        if not (
            condition.identity.source.origin_id == effect.identity.source.origin_id
            and condition.target_ref == target_ref
        )
    ]
    if not remaining_targets:
        state.ongoing_effects = [
            existing
            for existing in state.ongoing_effects
            if existing.identity.id != effect.identity.id
        ]
        _adjust_current_health_after_removal(state, previous_maximums)
        reconcile_remaining_attacks(state, (target_ref,))
        reconcile_remaining_movement(state, (target_ref,))
        return
    state.ongoing_effects = [
        replace(existing, target_refs=remaining_targets)
        if existing.identity.id == effect.identity.id
        else existing
        for existing in state.ongoing_effects
    ]
    _adjust_current_health_after_removal(state, previous_maximums)
    reconcile_remaining_attacks(state, (target_ref,))
    reconcile_remaining_movement(state, (target_ref,))


def _maximums_before_removal(
    state: EncounterState,
    effect: OngoingEffect,
    target_refs: tuple[str, ...],
) -> dict[str, int]:
    if not any(
        isinstance(rule_effect, MaximumHitPointAdjustment)
        and rule_effect.also_modify_current
        for rule_effect in effect.rule_effects
    ):
        return {}
    return {
        target_ref: effective_maximum_health(state, target_ref).value
        for target_ref in target_refs
    }


def _adjust_current_health_after_removal(
    state: EncounterState,
    previous_maximums: dict[str, int],
) -> None:
    for target_ref, previous_maximum in previous_maximums.items():
        creature = state.creatures[target_ref].creature
        maximum_delta = (
            effective_maximum_health(state, target_ref).value - previous_maximum
        )
        creature.current_health = max(0, creature.get_health() + maximum_delta)
