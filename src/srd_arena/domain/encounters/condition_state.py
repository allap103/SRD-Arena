"""Apply and remove sourced conditions from mutable encounter state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..effects.condition_rules import effective_conditions
from ..effects.conditions import (
    AppliedCondition,
    Condition,
    build_applied_condition,
)
from .effect_lifecycle.concentration import end_concentration
from .encounter_models.actions import CreatureRef
from .rule_queries.defenses import condition_immunities, condition_suppressions

if TYPE_CHECKING:
    from .encounter import EncounterState


@dataclass(frozen=True)
class ConditionRejection:
    """Explain why one requested condition application did not take hold."""

    condition: Condition
    reason: str


@dataclass(frozen=True)
class ConditionApplicationResult:
    """Report applied condition instances and rejected derived consequences."""

    requested_condition: Condition
    applied: tuple[AppliedCondition, ...] = ()
    rejections: tuple[ConditionRejection, ...] = ()

    @property
    def accepted(self) -> bool:
        """Return whether the requested condition was actually applied.

        >>> applied = build_applied_condition(condition=Condition.PRONE,
        ...     source_ref="fall", source_label="Fall", target_ref="hero")
        >>> ConditionApplicationResult(Condition.PRONE, (applied,)).accepted
        True
        >>> ConditionApplicationResult(Condition.PRONE).accepted
        False
        """
        return any(
            applied.condition is self.requested_condition for applied in self.applied
        )


def apply_condition(
    state: EncounterState,
    applied: AppliedCondition,
) -> ConditionApplicationResult:
    """Store one sourced condition application unless immunity prevents it.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     statistics=SimpleNamespace(condition_immunities=frozenset()),
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     conditions=[], relationships=[], ongoing_effects=[],
    ... )
    >>> applied = build_applied_condition(
    ...     condition=Condition.PRONE, source_ref="fall",
    ...     source_label="Fall", target_ref="hero",
    ... )
    >>> result = apply_condition(state, applied)
    >>> (result.accepted, state.conditions == [applied])
    (True, True)
    """

    immunities = condition_immunities(state, applied.target_ref).values
    if applied.condition in immunities:
        return ConditionApplicationResult(
            requested_condition=applied.condition,
            rejections=(ConditionRejection(applied.condition, "condition_immunity"),),
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
    suppressions = condition_suppressions(state, applied.target_ref).values
    if effective_conditions(target_conditions, suppressions).has(
        Condition.INCAPACITATED
    ):
        end_concentration(state, applied.target_ref)
    return ConditionApplicationResult(
        requested_condition=applied.condition,
        applied=tuple(consequences),
        rejections=rejections,
    )


def remove_condition(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
    *,
    removed_by_ref: CreatureRef | None = None,
) -> None:
    """Remove all applications of a condition kind from a creature.

    >>> from types import SimpleNamespace
    >>> applied = build_applied_condition(
    ...     condition=Condition.PRONE, source_ref="fall",
    ...     source_label="Fall", target_ref="hero",
    ... )
    >>> state = SimpleNamespace(conditions=[applied], relationships=[])
    >>> remove_condition(state, "hero", Condition.PRONE)
    >>> state.conditions
    []
    """

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
    """Remove only applications matching both condition kind and source identity.

    >>> from types import SimpleNamespace
    >>> first = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="ogre",
    ...     source_label="Ogre", target_ref="hero",
    ... )
    >>> second = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="snake",
    ...     source_label="Snake", target_ref="hero",
    ... )
    >>> state = SimpleNamespace(conditions=[first, second], relationships=[])
    >>> remove_condition_from_source(
    ...     state, "hero", Condition.GRAPPLED, source_ref="ogre"
    ... )
    >>> [condition.source_ref for condition in state.conditions]
    ['snake']
    """

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


def condition_sources_for(
    state: EncounterState,
    creature_ref: CreatureRef,
    condition: Condition,
) -> tuple[CreatureRef, ...]:
    """Return creatures responsible for matching condition applications.

    >>> from types import SimpleNamespace
    >>> applied = build_applied_condition(
    ...     condition=Condition.GRAPPLED, source_ref="ogre",
    ...     source_label="Ogre", target_ref="hero",
    ... )
    >>> condition_sources_for(
    ...     SimpleNamespace(conditions=[applied]), "hero", Condition.GRAPPLED
    ... )
    ('ogre',)
    """

    return tuple(
        applied.source_ref
        for applied in state.conditions
        if applied.target_ref == creature_ref
        and applied.condition is condition
        and applied.source_ref is not None
    )


def condition_replaces(
    existing: AppliedCondition,
    applied: AppliedCondition,
) -> bool:
    """Return whether a new application replaces the same runtime occurrence.

    >>> first = build_applied_condition(
    ...     condition=Condition.PRONE, source_ref="fall",
    ...     source_label="Fall", target_ref="hero",
    ... )
    >>> replacement = build_applied_condition(
    ...     condition=Condition.PRONE, source_ref="fall",
    ...     source_label="Fall", target_ref="hero",
    ... )
    >>> condition_replaces(first, replacement)
    True
    """

    return existing.id == applied.id
