"""Offer and resolve Parry against one exact pending melee hit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature, ParryReactionDefinition

from ..actions.pending_attacks import continue_pending_attack
from ..encounter_models.actions import ActionCost, EncounterAction
from ..encounter_models.decisions import (
    CloseParentDecision,
    DecisionContinuation,
    DecisionFrame,
)
from ..encounter_models.resolution import (
    AttackOutcome,
    DecisionExecutionResult,
    EncounterProgress,
    ParryRequest,
)
from ..rule_queries.permissions import reaction_eligibility
from ..state_runtime import create_event, next_action_id, next_frame_id

if TYPE_CHECKING:
    from ..encounter import EncounterState


def parry_definition_for(
    creature: Creature,
    attack_type: str,
) -> ParryReactionDefinition | None:
    """Return the creature's first Parry definition matching an attack mode."""

    return next(
        (
            definition
            for definition in creature.stat_block_actions.values()
            if isinstance(definition, ParryReactionDefinition)
            and attack_type in definition.trigger_attack_modes
        ),
        None,
    )


def open_parry_decision(
    state: EncounterState,
    *,
    attack: AttackOutcome,
    attacker_ref: str,
    target_ref: str,
    attacker_label: str,
    target_label: str,
    attack_name: str | None,
    attacks_remaining: int,
    action_id: str,
    progress: EncounterProgress,
    on_hit_feature_ids: tuple[str, ...] = (),
    continuation: DecisionContinuation | None = None,
    reaction_attack: bool = False,
) -> bool:
    """Suspend a matching hit before damage so its target may use Parry."""

    if not attack.hit:
        return False
    target = state.creatures[target_ref]
    definition = parry_definition_for(target.creature, attack.attack_type)
    if definition is None:
        return False
    eligibility = reaction_eligibility(state, target_ref, "parry")
    if not eligibility.allowed:
        return False
    target_ac = attack.attack_roll_detail.get("target_ac")
    if not isinstance(target_ac, int):
        raise RuntimeError("A pending Parry requires the attack's target AC.")

    request = ParryRequest(
        action_id=action_id,
        attacker_ref=attacker_ref,
        target_ref=target_ref,
        attacker_label=attacker_label,
        target_label=target_label,
        attack_name=attack_name,
        attacks_remaining=attacks_remaining,
        attack=attack,
        reaction_name=definition.name,
        armor_class_bonus=definition.armor_class_bonus,
        base_target_armor_class=target_ac,
        on_hit_feature_ids=on_hit_feature_ids,
        reaction_attack=reaction_attack,
    )
    current = state.current_decision()
    frame_id = next_frame_id(state, prefix="parry")
    state.interrupts.decision_stack.append(
        DecisionFrame(
            id=frame_id,
            creature_ref=target_ref,
            kind="parry",
            reason=definition.name,
            parent_frame_id=current.id,
            parent_action_id=action_id,
            can_pass=True,
            request=request,
            continuation=continuation,
        )
    )
    progress.messages.extend(attack.messages)
    attack.messages = []
    progress.messages.append(
        (
            "system",
            f"{target_label} can use {definition.name} against the hit.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "reaction_offered",
            creature_ref=target_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={
                "reaction": "parry",
                "reaction_name": definition.name,
                "attacker_ref": attacker_ref,
                "target_ref": target_ref,
                "attack_roll": attack.attack_roll,
                "base_target_armor_class": target_ac,
                "armor_class_bonus": definition.armor_class_bonus,
                "would_prevent_hit": request.would_prevent_hit,
            },
        )
    )
    progress.paused_for_decision = True
    return True


def parry_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer using Parry or preserving the target's Reaction."""

    decision = state.current_decision()
    request = _parry_request(decision)
    use = EncounterAction(
        f"Use {request.reaction_name}",
        "use_parry",
        id=f"{decision.id}-use",
        creature_ref=request.target_ref,
        cost=ActionCost(reaction=1),
    )
    decline = EncounterAction(
        "Do not parry",
        "decline_parry",
        id=f"{decision.id}-decline",
        creature_ref=request.target_ref,
    )
    return [use, decline] if request.would_prevent_hit else [decline, use]


def apply_parry_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Apply one Parry choice and continue the exact pending attack."""

    if action.kind not in {"use_parry", "decline_parry"}:
        raise ValueError("Parry choice must use or decline the reaction.")
    request = _parry_request(decision)
    progress = EncounterProgress()
    reaction_action_id = next_action_id(state)
    used = action.kind == "use_parry"
    prevented = False
    if used:
        eligibility = reaction_eligibility(state, request.target_ref, "parry")
        if not eligibility.allowed:
            raise ValueError(eligibility.failures[0].message)
        state.creatures[request.target_ref].reaction_available = False
        effective_ac = request.base_target_armor_class + request.armor_class_bonus
        request.attack.attack_roll_detail["parry_bonus"] = request.armor_class_bonus
        request.attack.attack_roll_detail["effective_target_ac"] = effective_ac
        prevented = request.would_prevent_hit
        if prevented:
            request.attack.hit = False
            request.attack.damage = 0
            request.attack.defender_defeated = False
            request.attack.critical_hit = False
            request.attack.damage_roll = None
            request.attack.damage_roll_detail = None
            request.attack.hit_effects = ()
            progress.messages.append(
                (
                    "system",
                    f"{request.target_label} uses {request.reaction_name}; "
                    "the attack misses.",
                )
            )
        else:
            progress.messages.append(
                (
                    "system",
                    f"{request.target_label} uses {request.reaction_name}, "
                    "but the attack still hits.",
                )
            )

    progress.events.append(
        create_event(
            state,
            "parry_resolved",
            creature_ref=request.target_ref,
            frame_id=decision.id,
            action_id=reaction_action_id,
            data={
                "pending_action_id": request.action_id,
                "attacker_ref": request.attacker_ref,
                "target_ref": request.target_ref,
                "used": used,
                "prevented_hit": prevented,
                "reaction_available": state.creatures[
                    request.target_ref
                ].reaction_available,
            },
        )
    )
    paused = continue_pending_attack(
        state,
        attack=request.attack,
        attacker_ref=request.attacker_ref,
        target_ref=request.target_ref,
        attacker_label=request.attacker_label,
        target_label=request.target_label,
        attack_name=request.attack_name,
        attacks_remaining=request.attacks_remaining,
        action_id=request.action_id,
        progress=progress,
        on_hit_feature_ids=request.on_hit_feature_ids,
        frame_id=decision.id,
        continuation=CloseParentDecision(
            frame_id=decision.id,
            action_id=reaction_action_id,
        ),
        reaction=request.reaction_attack,
    )
    return DecisionExecutionResult(
        progress=progress,
        action_id=reaction_action_id,
        completed=not paused,
    )


def _parry_request(decision: DecisionFrame) -> ParryRequest:
    if not isinstance(decision.request, ParryRequest):
        raise TypeError("Parry decision requires a Parry request.")
    return decision.request
