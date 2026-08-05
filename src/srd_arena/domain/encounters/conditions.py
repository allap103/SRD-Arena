from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..creatures import is_two_sizes_smaller
from ..effects.conditions import (
    AppliedCondition,
    Condition,
    build_applied_condition,
)
from ..effects.condition_rules import effective_conditions
from ..effects.runtime import (
    CreatureRelationship,
    RelationshipKind,
    RuntimeStateIdentity,
)
from ..geometry import MovementCost
from .models import CreatureRef

if TYPE_CHECKING:
    from .encounter import EncounterState


@dataclass(frozen=True)
class ConditionRejection:
    condition: Condition
    reason: str


@dataclass(frozen=True)
class ConditionApplicationResult:
    requested_condition: Condition
    applied: tuple[AppliedCondition, ...] = ()
    rejections: tuple[ConditionRejection, ...] = ()

    @property
    def accepted(self) -> bool:
        return any(
            applied.condition is self.requested_condition
            for applied in self.applied
        )


def apply_condition(
    state: EncounterState,
    applied: AppliedCondition,
) -> ConditionApplicationResult:
    target = state.creatures[applied.target_ref].creature
    if applied.condition in target.statistics.condition_immunities:
        return ConditionApplicationResult(
            requested_condition=applied.condition,
            rejections=(
                ConditionRejection(applied.condition, "condition_immunity"),
            ),
        )
    state.conditions = [
        existing
        for existing in state.conditions
        if not condition_replaces(existing, applied)
    ]
    state.conditions.append(applied)
    consequences: list[AppliedCondition] = [applied]
    if applied.condition is Condition.UNCONSCIOUS:
        prone = build_applied_condition(
            condition=Condition.PRONE,
            source_ref=applied.source_ref or applied.identity.source.definition_id,
            source_label=applied.source_label,
            target_ref=applied.target_ref,
            source_kind=applied.identity.source.kind,
            definition_id=applied.identity.source.definition_id,
            origin_id=applied.identity.source.origin_id,
            parent_id=applied.id,
            root_id=applied.identity.root_id,
        )
        prone_result = apply_condition(state, prone)
        consequences.extend(prone_result.applied)
        rejections = prone_result.rejections
    else:
        rejections = ()
    target_conditions = tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == applied.target_ref
    )
    if effective_conditions(
        target_conditions,
        target.statistics.condition_immunities,
    ).has(Condition.INCAPACITATED):
        from .ongoing_effects import end_concentration

        if hasattr(state, "ongoing_effects"):
            end_concentration(state, applied.target_ref)
    return ConditionApplicationResult(
        requested_condition=applied.condition,
        applied=tuple(consequences),
        rejections=rejections,
    )


def apply_grapple(
    state: EncounterState,
    applied: AppliedCondition,
) -> ConditionApplicationResult:
    if applied.condition is not Condition.GRAPPLED:
        raise ValueError("A grapple relationship requires Grappled.")
    source_ref = applied.source_ref
    if source_ref is None:
        raise ValueError("A grapple relationship requires a creature source.")
    result = apply_condition(state, applied)
    if not result.accepted:
        return result
    relationship_id = (
        f"relationship:grappling:{applied.identity.source.origin_id}:"
        f"{applied.target_ref}"
    )
    relationship = CreatureRelationship(
        identity=RuntimeStateIdentity(
            id=relationship_id,
            source=applied.identity.source,
            parent_id=applied.id,
            root_id=applied.identity.root_id,
        ),
        kind=RelationshipKind.GRAPPLING,
        source_ref=source_ref,
        target_ref=applied.target_ref,
        duration=applied.duration,
        metadata=dict(applied.metadata),
    )
    state.relationships = [
        existing
        for existing in state.relationships
        if not (
            existing.kind is RelationshipKind.GRAPPLING
            and existing.source_ref == relationship.source_ref
            and existing.target_ref == relationship.target_ref
        )
    ]
    state.relationships.append(relationship)
    return result


def remove_condition(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
    *,
    removed_by_ref: CreatureRef | None = None,
) -> None:
    remove_condition_from_source(
        state,
        target_ref,
        condition,
        removed_by_ref=removed_by_ref,
    )


def remove_condition_from_source(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
    source_ref: CreatureRef | None = None,
    *,
    removed_by_ref: CreatureRef | None = None,
) -> None:
    removed_ids = {
        applied.id
        for applied in state.conditions
        if applied.target_ref == target_ref
        and applied.condition is condition
        and (source_ref is None or applied.source_ref == source_ref)
        and not (
            removed_by_ref == target_ref
            and applied.metadata.get("blocks_self_removal") is True
        )
    }
    state.conditions = [
        applied for applied in state.conditions if applied.id not in removed_ids
    ]
    if removed_ids:
        state.relationships = [
            relationship
            for relationship in state.relationships
            if relationship.identity.parent_id not in removed_ids
        ]


def remove_relationships_for_creature(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    from .ongoing_effects import end_concentration

    if hasattr(state, "ongoing_effects"):
        end_concentration(state, creature_ref)
    grapple_condition_ids = {
        relationship.identity.parent_id
        for relationship in state.relationships
        if relationship.kind is RelationshipKind.GRAPPLING
        and (
            relationship.source_ref == creature_ref
            or relationship.target_ref == creature_ref
        )
        and relationship.identity.parent_id is not None
    }
    state.relationships = [
        relationship
        for relationship in state.relationships
        if not (
            relationship.kind is RelationshipKind.GRAPPLING
            and (
                relationship.source_ref == creature_ref
                or relationship.target_ref == creature_ref
            )
        )
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.id not in grapple_condition_ids
    ]


def condition_sources_for(
    state: EncounterState,
    creature_ref: CreatureRef,
    condition: Condition,
) -> tuple[CreatureRef, ...]:
    return tuple(
        applied.source_ref
        for applied in state.conditions
        if applied.target_ref == creature_ref
        and applied.condition is condition
        and applied.source_ref is not None
    )


def grappled_sources_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[CreatureRef, ...]:
    return condition_sources_for(state, creature_ref, Condition.GRAPPLED)


def grappling_targets_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[CreatureRef, ...]:
    return tuple(
        relationship.target_ref
        for relationship in state.relationships
        if relationship.kind is RelationshipKind.GRAPPLING
        and relationship.source_ref == creature_ref
    )


def is_grappled(state: EncounterState, creature_ref: CreatureRef) -> bool:
    return bool(grappled_sources_for(state, creature_ref))


def movement_cost_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> MovementCost | None:
    if is_grappled(state, creature_ref):
        return None
    cost = 1
    grappler_size = state._creature_size(creature_ref)
    for target_ref in grappling_targets_for(state, creature_ref):
        if not is_two_sizes_smaller(
            state._creature_size(target_ref),
            grappler_size,
        ):
            cost += 1
    return MovementCost(cost)


def condition_replaces(
    existing: AppliedCondition,
    applied: AppliedCondition,
) -> bool:
    return existing.id == applied.id
