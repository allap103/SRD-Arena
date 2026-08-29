"""Materialize authored ongoing effects in an encounter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.results import EffectResult
from ...effects.rule_effects import MaximumHitPointAdjustment
from ...effects.runtime import (
    EffectPolarity,
    EffectSource,
    EffectSourceKind,
    Indefinite,
    OngoingEffect,
    OngoingEffectKind,
    OngoingEffectLifecycle,
    Rounds,
    RuntimeStateIdentity,
)
from ..attack_economy import reconcile_remaining_attacks
from ..rule_queries.health import effective_maximum_health
from .concentration import end_concentration
from .movement import reconcile_remaining_movement
from .removal import _remove_effect_tree

if TYPE_CHECKING:
    from ..encounter import EncounterState


def start_ongoing_effect(
    state: EncounterState,
    result: EffectResult,
    origin_id: str,
) -> OngoingEffect:
    """Create encounter-owned ongoing state from one resolved effect.

    The runtime identity combines the effect kind with the exact action origin,
    allowing later removal to distinguish repeated uses of the same spell.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> result = EffectResult(
    ...     "ongoing_effect",
    ...     "target",
    ...     data={
    ...         "source_ref": "mage",
    ...         "source_label": "Mage",
    ...         "definition_id": "slow",
    ...         "effect_kind": "spell",
    ...     },
    ... )
    >>> creature = SimpleNamespace(
    ...     get_max_health=lambda: 10, get_health=lambda: 10,
    ...     current_health=10,
    ... )
    >>> state = SimpleNamespace(
    ...     ongoing_effects=[],
    ...     creatures={"target": SimpleNamespace(creature=creature)},
    ... )
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.application."
    ...     "reconcile_remaining_attacks"
    ... ), patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.application."
    ...     "reconcile_remaining_movement"
    ... ):
    ...     effect = start_ongoing_effect(state, result, "cast-7")
    >>> (effect.identity.id, effect.target_refs, state.ongoing_effects == [effect])
    ('ongoing:spell:cast-7', ('target',), True)
    """

    source_ref = _required_string(result, "source_ref")
    source_label = _required_string(result, "source_label")
    definition_id = _required_string(result, "definition_id")
    kind = OngoingEffectKind(_required_string(result, "effect_kind"))
    polarity = EffectPolarity(str(result.data.get("polarity", "neutral")))
    if kind is OngoingEffectKind.CONCENTRATION:
        end_concentration(state, source_ref)
    source = EffectSource(
        kind=EffectSourceKind.SPELL,
        definition_id=definition_id,
        applied_by_ref=source_ref,
        label=source_label,
        origin_id=origin_id,
    )
    if bool(result.data.get("recast_ends_previous", False)):
        previous = tuple(
            effect
            for effect in state.ongoing_effects
            if effect.identity.source.definition_id == definition_id
            and effect.identity.source.applied_by_ref == source_ref
        )
        for effect in previous:
            _remove_effect_tree(state, effect)
    duration_rounds = result.data.get("duration_rounds")
    target_refs_data = result.data.get("target_refs")
    target_refs = (
        tuple(ref for ref in target_refs_data if isinstance(ref, str))
        if isinstance(target_refs_data, list)
        else (result.target_ref,)
    )
    previous_maximums = {
        target_ref: effective_maximum_health(state, target_ref).value
        for target_ref in target_refs
    }
    effect = OngoingEffect(
        identity=RuntimeStateIdentity(
            id=f"ongoing:{kind.value}:{origin_id}",
            source=source,
        ),
        target_refs=target_refs,
        duration=(
            Rounds(duration_rounds)
            if isinstance(duration_rounds, int)
            else Indefinite()
        ),
        kind=kind,
        polarity=polarity,
        label=result.effect_label,
        lifecycle=result.lifecycle or OngoingEffectLifecycle(),
        dispellable=True,
        rule_effects=result.rule_effects,
    )
    state.ongoing_effects.append(effect)
    reconcile_remaining_attacks(state, target_refs)
    reconcile_remaining_movement(state, target_refs)
    if any(
        isinstance(rule_effect, MaximumHitPointAdjustment)
        and rule_effect.also_modify_current
        for rule_effect in effect.rule_effects
    ):
        for target_ref in target_refs:
            creature = state.creatures[target_ref].creature
            maximum_delta = (
                effective_maximum_health(state, target_ref).value
                - previous_maximums[target_ref]
            )
            creature.current_health = max(0, creature.get_health() + maximum_delta)
    return effect


def _required_string(result: EffectResult, key: str) -> str:
    value = result.data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Ongoing effect requires string {key}.")
    return value
