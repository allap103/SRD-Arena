"""Query grapple relationships and their effect on encounter movement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import is_two_sizes_smaller
from ..effects.conditions import AppliedCondition, Condition
from ..effects.runtime import (
    CreatureRelationship,
    RelationshipKind,
    RuntimeStateIdentity,
)
from ..geometry import MovementCost
from .condition_state import (
    ConditionApplicationResult,
    apply_condition,
    condition_sources_for,
)
from .encounter_models.actions import CreatureRef
from .state_runtime import creature_size

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_grapple(
    state: EncounterState,
    applied: AppliedCondition,
) -> ConditionApplicationResult:
    """Apply Grappled to a target and record the grappler-target relationship.

    >>> from types import SimpleNamespace
    >>> from ..effects.conditions import build_applied_condition
    >>> creature = SimpleNamespace(
    ...     statistics=SimpleNamespace(condition_immunities=frozenset()),
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     conditions=[], relationships=[], ongoing_effects=[],
    ... )
    >>> applied = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="ogre",
    ...     source_label="Ogre", target_ref="hero",
    ... )
    >>> result = apply_grapple(state, applied)
    >>> (result.accepted, state.relationships[0].source_ref)
    (True, 'ogre')
    """

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


def remove_relationships_for_creature(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    """End grapple relationships in which a removed creature appears on either side.

    >>> from types import SimpleNamespace
    >>> relationship = SimpleNamespace(
    ...     kind=RelationshipKind.GRAPPLING, source_ref="ogre",
    ...     target_ref="hero", identity=SimpleNamespace(parent_id="condition-1"),
    ... )
    >>> condition = SimpleNamespace(id="condition-1")
    >>> state = SimpleNamespace(
    ...     relationships=[relationship], conditions=[condition],
    ...     ongoing_effects=[],
    ... )
    >>> remove_relationships_for_creature(state, "ogre")
    >>> (state.relationships, state.conditions)
    ([], [])
    """

    from .ongoing_effects import end_concentration

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


def grappled_sources_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[CreatureRef, ...]:
    """Return creatures currently imposing Grappled on the target.

    >>> from types import SimpleNamespace
    >>> from ..effects.conditions import build_applied_condition
    >>> condition = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="ogre",
    ...     source_label="Ogre", target_ref="hero",
    ... )
    >>> grappled_sources_for(SimpleNamespace(conditions=[condition]), "hero")
    ('ogre',)
    """

    return condition_sources_for(state, creature_ref, Condition.GRAPPLED)


def grappling_targets_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[CreatureRef, ...]:
    """Return creatures currently grappled by the source.

    >>> from types import SimpleNamespace
    >>> relationship = SimpleNamespace(
    ...     kind=RelationshipKind.GRAPPLING,
    ...     source_ref="ogre", target_ref="hero",
    ... )
    >>> grappling_targets_for(
    ...     SimpleNamespace(relationships=[relationship]), "ogre"
    ... )
    ('hero',)
    """

    return tuple(
        relationship.target_ref
        for relationship in state.relationships
        if relationship.kind is RelationshipKind.GRAPPLING
        and relationship.source_ref == creature_ref
    )


def is_grappled(state: EncounterState, creature_ref: CreatureRef) -> bool:
    """Return whether any active source currently grapples the creature.

    >>> from types import SimpleNamespace
    >>> from ..effects.conditions import build_applied_condition
    >>> condition = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="ogre",
    ...     source_label="Ogre", target_ref="hero",
    ... )
    >>> is_grappled(SimpleNamespace(conditions=[condition]), "hero")
    True
    """

    return bool(grappled_sources_for(state, creature_ref))


def movement_cost_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> MovementCost | None:
    """Include the cost of dragging grappled creatures in a movement step.

    >>> from types import SimpleNamespace
    >>> relationship = SimpleNamespace(
    ...     kind=RelationshipKind.GRAPPLING,
    ...     source_ref="ogre", target_ref="hero",
    ... )
    >>> state = SimpleNamespace(
    ...     conditions=[], relationships=[relationship],
    ...     creatures={
    ...         "ogre": SimpleNamespace(creature=SimpleNamespace(size="L")),
    ...         "hero": SimpleNamespace(creature=SimpleNamespace(size="M")),
    ...     },
    ... )
    >>> movement_cost_for(state, "ogre")
    2
    """

    if is_grappled(state, creature_ref):
        return None
    cost = 1
    grappler_size = creature_size(state, creature_ref)
    for target_ref in grappling_targets_for(state, creature_ref):
        if not is_two_sizes_smaller(
            creature_size(state, target_ref),
            grappler_size,
        ):
            cost += 1
    return MovementCost(cost)
