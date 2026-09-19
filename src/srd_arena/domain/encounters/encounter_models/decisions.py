"""Typed decision requests, continuations, and suspended selection state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from srd_arena.domain.creatures.attributes import MovementMode
from srd_arena.domain.effects.results import ActionResolutionResult
from srd_arena.domain.geometry import MovementBudget, MovementCost, Position
from srd_arena.domain.rolls.dice import D20RollMode
from srd_arena.domain.spells.action_payloads import SpellActionPayload

from .actions import CreatureRef

if TYPE_CHECKING:
    from .resolution import ActionExecutionContext


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
    movement_mode: MovementMode = "walk"


@dataclass(frozen=True)
class OpportunityAttackRequest(DecisionRequest):
    """Offer reactions against one exact suspended movement occurrence."""

    movement: PendingMovement


@dataclass(frozen=True)
class GrappleSaveRequest(DecisionRequest):
    """Ask one target how to resist an exact grapple attempt."""

    action_id: str
    grappler_ref: CreatureRef
    target_ref: CreatureRef
    save_dc: int


@dataclass(frozen=True)
class ForcedMovementChoiceRequest(DecisionRequest):
    """Ask a source whether and how far to move one target after a trigger."""

    action_id: str
    source_ref: CreatureRef
    target_ref: CreatureRef
    direction: Literal["away", "toward"]
    maximum_distance_feet: int
    source_id: str
    source_label: str
    occurrence_index: int = 1


@dataclass(frozen=True)
class InitiativeSwapRequest(DecisionRequest):
    """Offer one Alert owner its optional post-roll Initiative swap."""

    owner_ref: CreatureRef


@dataclass(frozen=True)
class D20RollOccurrence:
    """Identify one future D20 Test or incoming attack roll within an action."""

    id: str
    kind: Literal["attack_roll", "saving_throw", "ability_check"]
    roller_ref: CreatureRef
    target_ref: CreatureRef | None
    label: str


@dataclass(frozen=True)
class LuckyRollOption:
    """Offer one Lucky owner a roll-mode change for one exact occurrence."""

    owner_ref: CreatureRef
    occurrence: D20RollOccurrence
    mode: Literal["advantage", "disadvantage"]


@dataclass
class PendingD20RollModifiers:
    """Accumulate optional roll-mode changes before an action resumes."""

    action_id: str
    options: tuple[LuckyRollOption, ...]
    selected_modes: dict[str, list[D20RollMode]] = field(default_factory=dict)
    option_index: int = 0

    @property
    def current_option(self) -> LuckyRollOption:
        """Return the optional modifier currently awaiting a controller choice."""

        return self.options[self.option_index]


@dataclass(frozen=True)
class D20RollModifierRequest(DecisionRequest):
    """Ask a feature owner whether to modify one addressed D20 roll."""

    pending: PendingD20RollModifiers


@dataclass(frozen=True)
class RecklessAttackRequest(DecisionRequest):
    """Ask whether the actor makes its first eligible attack recklessly."""

    action_id: str
    actor_ref: CreatureRef


@dataclass(frozen=True)
class WeaponMasteryRequest(DecisionRequest):
    """Offer one usable mastery after an exact weapon attack has hit."""

    action_id: str
    attacker_ref: CreatureRef
    target_ref: CreatureRef
    mastery: str
    weapon_id: str
    weapon_name: str
    save_dc: int | None = None


@dataclass
class PendingSpellProjectiles:
    """Preserve one started spell while its projectiles and choices resolve."""

    invocation_id: str
    caster_ref: CreatureRef
    spell_id: str
    cast_level: int | None
    payload: SpellActionPayload
    target_refs: tuple[CreatureRef, ...]
    target_labels: tuple[str, ...]
    remaining_target_refs: list[CreatureRef]
    resolved_results: list[ActionResolutionResult] = field(default_factory=list)
    cast_announced: bool = False


@dataclass(frozen=True)
class ResumeMovement(DecisionContinuation):
    """Resume a suspended movement after its reaction decision closes."""

    movement: PendingMovement


@dataclass(frozen=True)
class ResumeSpellProjectiles(DecisionContinuation):
    """Resume the exact spell invocation after an interrupting choice closes."""

    invocation: PendingSpellProjectiles


@dataclass(frozen=True)
class ResumeActionExecution(DecisionContinuation):
    """Resume a declared creature action after its pre-roll choices."""

    context: ActionExecutionContext


@dataclass(frozen=True)
class ResumeSpellInvocation(DecisionContinuation):
    """Resume a targeted spell after its pre-roll choices."""

    caster_ref: CreatureRef
    payload: SpellActionPayload
    action_id: str


@dataclass(frozen=True)
class ResumeWeaponMastery(DecisionContinuation):
    """Open a post-hit mastery after an earlier attack decision completes."""

    request: WeaponMasteryRequest
    next_continuation: DecisionContinuation | None = None


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
class InterruptState:
    """Own nested decisions arising during game resolution."""

    decision_stack: list[DecisionFrame] = field(default_factory=list)
