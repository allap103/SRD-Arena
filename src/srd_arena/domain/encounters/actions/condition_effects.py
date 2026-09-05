"""Apply sourced condition effects shared by attacks and save-based actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import ConditionEffect, SizeRequirement
from srd_arena.domain.creatures import size_rank
from srd_arena.domain.effects.application import condition_from_effect_with_origin
from srd_arena.domain.effects.conditions import (
    Condition,
    DestructibleConditionState,
    build_applied_condition,
)
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


def apply_sourced_condition_effect(
    state: EncounterState,
    *,
    source_ref: str,
    target_ref: str,
    effect: ConditionEffect,
    progress: EncounterProgress,
    origin_id: str,
    definition_id: str,
    originating_action: str,
) -> bool:
    """Apply one supported condition effect with source and occurrence identity.

    The common boundary keeps Grappled relationship creation, source capacity,
    size gates, duration calculation, and immunity behavior identical whether
    an effect follows an attack roll or a saving throw.
    """

    source = state.creatures[source_ref].creature
    target = state.creatures[target_ref].creature
    if not target_meets_condition_size_requirements(target.size, effect):
        return False
    if effect.condition != "grappled":
        result = apply_condition(
            state,
            build_applied_condition(
                condition=Condition(effect.condition),
                source_ref=source_ref,
                source_label=source.name,
                target_ref=target_ref,
                source_kind=EffectSourceKind.ACTION,
                definition_id=definition_id,
                origin_id=origin_id,
                duration=condition_effect_duration(
                    state,
                    source_ref,
                    target_ref,
                    effect,
                ),
                destructible=(
                    DestructibleConditionState(
                        label=effect.destructible.label,
                        armor_class=effect.destructible.armor_class,
                        hit_points=effect.destructible.hit_points,
                        maximum_hit_points=effect.destructible.hit_points,
                        damage_vulnerabilities=frozenset(
                            damage_type.casefold()
                            for damage_type in (
                                effect.destructible.damage_vulnerabilities
                            )
                        ),
                        damage_immunities=frozenset(
                            damage_type.casefold()
                            for damage_type in effect.destructible.damage_immunities
                        ),
                    )
                    if effect.destructible is not None
                    else None
                ),
            ),
        )
        if result.accepted:
            progress.messages.append(
                ("system", f"{target.name} is {effect.condition}.")
            )
        return result.accepted

    already_grappled = source_ref in grappled_sources_for(state, target_ref)
    capacity = effect.source_capacity
    if (
        not already_grappled
        and isinstance(capacity, int)
        and len(grappling_targets_for(state, source_ref)) >= capacity
    ):
        return False
    metadata = {
        "escape_dc": effect.escape_dc,
        "originating_action": originating_action,
    }
    result = apply_grapple(
        state,
        condition_from_effect_with_origin(
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": source_ref,
                    "source_label": source.name,
                    "source_kind": "action",
                    "definition_id": definition_id,
                    "metadata": metadata,
                },
            ),
            origin_id=origin_id,
        ),
    )
    if result.accepted:
        progress.messages.append(("system", f"{source.name} grapples {target.name}."))
    return result.accepted


def target_meets_condition_size_requirements(
    target_size: str,
    effect: ConditionEffect,
) -> bool:
    """Return whether every effect-level size requirement includes the target."""

    for requirement in effect.requirements:
        if not isinstance(requirement, SizeRequirement):
            return False
        if requirement.maximum is not None and size_rank(target_size) > size_rank(
            requirement.maximum
        ):
            return False
        if requirement.minimum is not None and size_rank(target_size) < size_rank(
            requirement.minimum
        ):
            return False
    return True


def condition_effect_duration(
    state: EncounterState,
    source_ref: str,
    target_ref: str,
    effect: ConditionEffect,
) -> EffectDuration:
    """Translate a capability's relative condition duration into encounter time."""

    duration = effect.duration
    if duration is None:
        return Indefinite()
    creature_ref = source_ref if duration.creature == "source" else target_ref
    round_number = state.round.number + duration.turn_offset
    if duration.kind == "start_of_turn":
        return UntilTurnStart(creature_ref, round_number)
    if duration.kind == "end_of_turn":
        return UntilTurnEnd(creature_ref, round_number)
    return Indefinite()
