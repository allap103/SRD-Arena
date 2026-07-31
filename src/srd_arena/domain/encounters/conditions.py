from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import is_two_sizes_smaller
from ..effects.conditions import AppliedCondition, Condition
from ..effects.runtime import (
    CreatureRelationship,
    RelationshipKind,
    RuntimeStateIdentity,
)
from .models import CreatureRef

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_condition(
    state: EncounterState,
    applied: AppliedCondition,
) -> None:
    state.conditions = [
        existing
        for existing in state.conditions
        if not condition_replaces(existing, applied)
    ]
    state.conditions.append(applied)


def apply_grapple(
    state: EncounterState,
    applied: AppliedCondition,
) -> None:
    if applied.condition is not Condition.GRAPPLED:
        raise ValueError("A grapple relationship requires Grappled.")
    source_ref = applied.source_ref
    if source_ref is None:
        raise ValueError("A grapple relationship requires a creature source.")
    apply_condition(state, applied)
    relationship_id = f"relationship:grappling:{source_ref}:{applied.target_ref}"
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


def remove_condition(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
) -> None:
    remove_condition_from_source(state, target_ref, condition)


def remove_condition_from_source(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
    source_ref: CreatureRef | None = None,
) -> None:
    removed_ids = {
        applied.id
        for applied in state.conditions
        if applied.target_ref == target_ref
        and applied.condition is condition
        and (source_ref is None or applied.source_ref == source_ref)
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
) -> int | None:
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
    return cost


def condition_replaces(
    existing: AppliedCondition,
    applied: AppliedCondition,
) -> bool:
    if (
        existing.condition is not applied.condition
        or existing.target_ref != applied.target_ref
    ):
        return False
    if existing.condition is Condition.GRAPPLED:
        return existing.source_ref == applied.source_ref
    return True
