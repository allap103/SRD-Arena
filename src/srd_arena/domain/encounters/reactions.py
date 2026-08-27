"""Stable coordinator for encounter reaction mechanics.

Opportunity Attacks, damage rerolls, and attack lifecycle consequences live
in focused :mod:`reaction_runtime` modules.  This facade retains the service
API consumed by encounter orchestration and continuation handling.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ..effects.triggered import TriggeredEffect
from ..geometry import MovementBudget, MovementCost, Position
from .models import (
    AttackOutcome,
    DamageRerollRequest,
    DecisionContinuation,
    DecisionExecutionResult,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
    PendingMovement,
)

if TYPE_CHECKING:
    from .encounter import EncounterState

from .reaction_runtime.attack_lifecycle import (
    resolve_attack_lifecycle as _resolve_attack_lifecycle,
)
from .reaction_runtime.damage_rerolls import (
    apply_damage_reroll_action as _apply_damage_reroll_action,
)
from .reaction_runtime.damage_rerolls import (
    damage_reroll_event_data as _damage_reroll_event_data,
)
from .reaction_runtime.damage_rerolls import (
    damage_reroll_request as _damage_reroll_request,
)
from .reaction_runtime.damage_rerolls import (
    finalize_damage_reroll as _finalize_damage_reroll,
)
from .reaction_runtime.damage_rerolls import (
    open_damage_reroll_decision as _open_damage_reroll_decision,
)
from .reaction_runtime.damage_rerolls import (
    reroll_damage_actions as _reroll_damage_actions,
)
from .reaction_runtime.opportunity_attacks import (
    apply_reaction_action as _apply_reaction_action,
)
from .reaction_runtime.opportunity_attacks import (
    opportunity_attack_request as _opportunity_attack_request,
)
from .reaction_runtime.opportunity_attacks import (
    queue_opportunity_attack as _queue_opportunity_attack,
)
from .reaction_runtime.opportunity_attacks import (
    reaction_actions as _reaction_actions,
)
from .reaction_runtime.opportunity_attacks import (
    resolve_automatic_opportunity_attacks as _resolve_automatic_opportunity_attacks,
)
from .reaction_runtime.opportunity_attacks import (
    resume_movement as _resume_movement,
)


def _roll_die(sides: int) -> int:
    """Roll through the encounter module's runtime-patchable dice seam."""

    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    """Roll damage through the encounter module's patchable dice seam."""

    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


class ReactionEngine:
    """Coordinate reaction offers while the orchestrator owns continuation."""

    def resolve_automatic_opportunity_attacks(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        from_position: Position,
        to_position: Position,
        action_id: str,
        progress: EncounterProgress,
        excluded_reactor_refs: Collection[str] = (),
    ) -> list[tuple[str, str]]:
        return _resolve_automatic_opportunity_attacks(
            state,
            mover_ref=mover_ref,
            from_position=from_position,
            to_position=to_position,
            action_id=action_id,
            progress=progress,
            excluded_reactor_refs=excluded_reactor_refs,
        )

    def open_damage_reroll_decision(
        self,
        state: EncounterState,
        *,
        attack: AttackOutcome,
        triggered_effect: TriggeredEffect,
        attacker_ref: str,
        target_ref: str,
        attacker_label: str,
        target_label: str,
        action_id: str,
        progress: EncounterProgress,
        continuation: DecisionContinuation | None = None,
        reaction: bool = False,
    ) -> None:
        _open_damage_reroll_decision(
            state,
            attack=attack,
            triggered_effect=triggered_effect,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            attacker_label=attacker_label,
            target_label=target_label,
            action_id=action_id,
            progress=progress,
            continuation=continuation,
            reaction=reaction,
        )

    def reroll_damage_actions(self, state: EncounterState) -> list[EncounterAction]:
        return _reroll_damage_actions(state)

    def apply_damage_reroll_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        return _apply_damage_reroll_action(state, action, decision)

    def finalize_damage_reroll(
        self,
        state: EncounterState,
        request: DamageRerollRequest,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        _finalize_damage_reroll(state, request, progress, decision)

    def damage_reroll_event_data(
        self,
        request: DamageRerollRequest,
    ) -> dict[str, object]:
        return _damage_reroll_event_data(request)

    def apply_reaction_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        return _apply_reaction_action(
            state,
            action,
            decision,
            open_damage_reroll=self.open_damage_reroll_decision,
        )

    def resume_movement(
        self,
        state: EncounterState,
        movement: PendingMovement,
        progress: EncounterProgress,
    ) -> None:
        _resume_movement(state, movement, progress)

    def queue_opportunity_attack(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: MovementBudget,
        movement_cost: MovementCost,
        companion_destinations: dict[str, Position],
        progress: EncounterProgress,
        external_only: bool,
        excluded_reactor_refs: Collection[str] = (),
    ) -> bool:
        return _queue_opportunity_attack(
            state,
            mover_ref=mover_ref,
            action_id=action_id,
            direction=direction,
            from_position=from_position,
            to_position=to_position,
            remaining_movement_after=remaining_movement_after,
            movement_cost=movement_cost,
            companion_destinations=companion_destinations,
            progress=progress,
            external_only=external_only,
            excluded_reactor_refs=excluded_reactor_refs,
        )

    def reaction_actions(self, state: EncounterState) -> list[EncounterAction]:
        return _reaction_actions(state)


REACTION_ENGINE = ReactionEngine()

__all__ = [
    "REACTION_ENGINE",
    "ReactionEngine",
    "_damage_reroll_request",
    "_opportunity_attack_request",
    "_resolve_attack_lifecycle",
    "_roll_dice",
    "_roll_die",
]
