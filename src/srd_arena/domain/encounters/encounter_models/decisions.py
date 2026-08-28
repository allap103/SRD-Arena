"""Typed decision requests, continuations, and suspended selection state."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry import MovementBudget, MovementCost, Position
from .actions import CreatureRef, EncounterAction


class DecisionRequest:
    """Typed state needed to resolve a decision frame."""


class DecisionContinuation:
    """Typed work resumed after a decision frame closes."""


@dataclass
class PendingMovement:
    """One movement suspended while an interrupt decision resolves."""

    action_id: str
    creature_ref: CreatureRef
    direction: str
    from_position: Position
    to_position: Position
    remaining_movement_after: MovementBudget
    movement_cost: MovementCost
    trigger_id: str
    companion_destinations: dict[CreatureRef, Position] = field(default_factory=dict)


@dataclass(frozen=True)
class OpportunityAttackRequest(DecisionRequest):
    """Offer reactions against one exact suspended movement occurrence."""

    movement: PendingMovement


@dataclass(frozen=True)
class ResumeMovement(DecisionContinuation):
    """Resume a suspended movement after its reaction decision closes."""

    movement: PendingMovement


@dataclass(frozen=True)
class CloseParentDecision(DecisionContinuation):
    """Close a specific parent frame after a nested decision resolves.

    Referencing the exact frame and action occurrence allows reactions such as
    nested Counterspells to unwind safely in last-in, first-out order.
    """

    frame_id: str
    action_id: str


@dataclass
class DecisionFrame:
    """Track one unresolved controller choice on the encounter decision stack."""

    id: str
    creature_ref: CreatureRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False
    request: DecisionRequest | None = None
    continuation: DecisionContinuation | None = None


@dataclass
class PendingSpellCast:
    """Pre-invocation spell selection state; casting has not started yet."""

    action: EncounterAction
    spell_id: str
    selected_target_refs: list[CreatureRef]
    maximum_targets: int
    repeat_target_allocations: bool = False
    require_full_target_count: bool = False
    resource_pool_total: int | None = None
    resource_allocations: dict[CreatureRef, int] = field(default_factory=dict)
    resource_allocation_limits: dict[CreatureRef, int] = field(default_factory=dict)


@dataclass
class InterruptState:
    """Own nested decision frames and spell targeting staged before invocation."""

    decision_stack: list[DecisionFrame] = field(default_factory=list)
    pending_spell_cast: PendingSpellCast | None = None
