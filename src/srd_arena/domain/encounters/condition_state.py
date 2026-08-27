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
from .models import CreatureRef

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
    """Apply condition."""

    target = state.creatures[applied.target_ref].creature
    if applied.condition in target.condition_immunities():
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


def remove_condition(
    state: EncounterState,
    target_ref: CreatureRef,
    condition: Condition,
    *,
    removed_by_ref: CreatureRef | None = None,
) -> None:
    """Remove condition."""

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
    """Remove condition from source."""

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
    """Return creatures responsible for matching condition applications."""

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
    """Return whether a new application replaces the same runtime occurrence."""

    return existing.id == applied.id
