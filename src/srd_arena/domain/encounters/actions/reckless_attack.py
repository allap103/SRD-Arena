"""Offer and apply the optional Reckless Attack pre-roll decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures.feature_rules import (
    has_reckless_attack,
    reckless_attack_result,
)

from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import (
    DecisionContinuation,
    DecisionFrame,
    RecklessAttackRequest,
)
from ..encounter_models.resolution import DecisionExecutionResult, EncounterProgress
from ..state_runtime import apply_encounter_effects, create_event, next_frame_id
from .attack_resolution import selected_attack_ability

if TYPE_CHECKING:
    from ..encounter import EncounterState


def open_reckless_attack_decision(
    state: EncounterState,
    action: EncounterAction,
    *,
    actor_ref: str,
    action_id: str,
    continuation: DecisionContinuation,
    progress: EncounterProgress,
) -> bool:
    """Suspend the actor's first Strength-based attack for its optional choice."""

    actor_state = state.creatures[actor_ref]
    if (
        action.kind not in {"attack", "attack_condition"}
        or actor_state.attack_rolls_made_this_turn != 0
        or not has_reckless_attack(actor_state.creature)
        or selected_attack_ability(
            actor_state.creature,
            state.item_templates,
            preferred_attack_type=action.preferred_attack_type,
            preferred_attack_name=action.preferred_attack_name,
        )
        != "strength"
    ):
        return False
    frame_id = next_frame_id(state, prefix="reckless_attack")
    state.interrupts.decision_stack.append(
        DecisionFrame(
            id=frame_id,
            creature_ref=actor_ref,
            kind="reckless_attack",
            reason="first_strength_attack_roll",
            request=RecklessAttackRequest(action_id, actor_ref),
            continuation=continuation,
        )
    )
    progress.paused_for_decision = True
    progress.events.append(
        create_event(
            state,
            "decision_opened",
            creature_ref=actor_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={"kind": "reckless_attack", "feature_id": "reckless_attack"},
        )
    )
    return True


def reckless_attack_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer using Reckless Attack or resolving the attack normally."""

    decision = state.current_decision()
    request = _request(decision)
    return [
        EncounterAction(
            "Use Reckless Attack",
            "use_reckless_attack",
            id=f"{decision.id}-use",
            creature_ref=request.actor_ref,
        ),
        EncounterAction(
            "Attack normally",
            "decline_reckless_attack",
            id=f"{decision.id}-decline",
            creature_ref=request.actor_ref,
        ),
    ]


def apply_reckless_attack_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Apply the Reckless Attack choice and resume the exact pending attack."""

    if action.kind not in {"use_reckless_attack", "decline_reckless_attack"}:
        raise ValueError("Reckless Attack choice must use or decline the feature.")
    request = _request(decision)
    progress = EncounterProgress()
    used = action.kind == "use_reckless_attack"
    if used:
        creature = state.creatures[request.actor_ref].creature
        result = reckless_attack_result(
            creature,
            request.actor_ref,
            state.round.number,
        )
        progress.messages.extend(result.messages)
        progress.messages.extend(
            apply_encounter_effects(
                state,
                result.effects,
                origin_id=f"{request.action_id}:reckless_attack",
            )
        )
    progress.events.append(
        create_event(
            state,
            "reckless_attack_resolved",
            creature_ref=request.actor_ref,
            frame_id=decision.id,
            action_id=request.action_id,
            data={"feature_id": "reckless_attack", "used": used},
        )
    )
    return DecisionExecutionResult(progress, action.id, completed=True)


def _request(decision: DecisionFrame) -> RecklessAttackRequest:
    if not isinstance(decision.request, RecklessAttackRequest):
        raise TypeError("Reckless Attack decision requires its typed request.")
    return decision.request
