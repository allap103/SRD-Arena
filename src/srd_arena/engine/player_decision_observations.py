"""Describe owned interrupts using an explicit allowlist of public facts."""

from srd_arena.domain.encounters.encounter_models.decisions import (
    D20RollModifierRequest,
    DecisionFrame,
    ForcedMovementChoiceRequest,
    GrappleSaveRequest,
    InitiativeSwapRequest,
    OpportunityAttackRequest,
    RecklessAttackRequest,
    WeaponMasteryRequest,
)
from srd_arena.domain.encounters.encounter_models.resolution import (
    DamageRerollRequest,
    ParryRequest,
)

from .player_observation_models import PlayerDecisionContext


def observe_player_decision(
    decision: DecisionFrame,
    *,
    allied_refs: frozenset[str],
    visible_refs: frozenset[str],
) -> PlayerDecisionContext | None:
    """Return safe trigger context only to the team answering this decision.

    Unknown request types fail closed. No generic serialization of requests,
    labels, reasons, attack results, or nested continuations is permitted.
    """

    if decision.creature_ref not in allied_refs:
        return None
    request = decision.request
    actor: str | None = None
    target: str | None = None
    roll_kind: str | None = None
    mode: str | None = None
    if isinstance(request, OpportunityAttackRequest):
        trigger = "opportunity_attack"
        actor = request.movement.creature_ref
    elif isinstance(request, D20RollModifierRequest):
        trigger = "d20_roll_modifier"
        option = request.pending.current_option
        if option.owner_ref != decision.creature_ref:
            return None
        actor = option.occurrence.roller_ref
        target = option.occurrence.target_ref
        roll_kind = option.occurrence.kind
        mode = option.mode
    elif isinstance(request, GrappleSaveRequest):
        trigger = "grapple_save"
        actor, target = request.grappler_ref, request.target_ref
        roll_kind = "saving_throw"
    elif isinstance(request, ForcedMovementChoiceRequest):
        trigger = "forced_movement"
        actor, target = request.source_ref, request.target_ref
    elif isinstance(request, WeaponMasteryRequest):
        trigger = "weapon_mastery"
        actor, target = request.attacker_ref, request.target_ref
    elif isinstance(request, RecklessAttackRequest):
        trigger = "reckless_attack"
        actor = request.actor_ref
        roll_kind = "attack_roll"
    elif isinstance(request, InitiativeSwapRequest):
        trigger = "initiative_swap"
        actor = request.owner_ref
    elif isinstance(request, ParryRequest):
        trigger = "parry"
        actor, target = request.attacker_ref, request.target_ref
    elif isinstance(request, DamageRerollRequest):
        trigger = "damage_reroll"
        actor, target = request.attacker_ref, request.target_ref
    else:
        return None
    return PlayerDecisionContext(
        trigger=trigger,
        can_pass=decision.can_pass,
        actor_ref=actor if actor in visible_refs else None,
        target_ref=target if target in visible_refs else None,
        roll_kind=roll_kind,
        offered_roll_mode=mode,
    )
