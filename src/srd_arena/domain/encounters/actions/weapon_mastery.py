"""Offer and resolve optional effects of mastered weapon attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.effects.rule_effects import SpeedAdjustment
from srd_arena.domain.effects.runtime import EffectSourceKind, UntilTurnStart
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw

from ..condition_state import apply_condition
from ..effect_lifecycle.lifecycle_events import resolve_effect_lifecycle_event
from ..effect_lifecycle.roll_usage import resolve_saving_throw_modifier
from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import (
    DecisionContinuation,
    DecisionFrame,
    WeaponMasteryRequest,
)
from ..encounter_models.resolution import (
    AttackOutcome,
    DecisionExecutionResult,
    EncounterProgress,
)
from ..rule_queries.defenses import has_condition_save_advantage
from ..rule_queries.rolls import roll_modifiers
from ..state_combat import automatic_save_failure_provider_ids_for
from ..state_runtime import (
    apply_encounter_effects,
    create_event,
    creature_label,
    next_frame_id,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def mastery_request_for_attack(
    state: EncounterState,
    attack: AttackOutcome,
    *,
    attacker_ref: str,
    target_ref: str,
    action_id: str,
) -> WeaponMasteryRequest | None:
    """Build a supported post-hit mastery request for one resolved attack."""

    mastery = attack.weapon_mastery
    if not attack.hit or not state.creatures[target_ref].is_alive:
        return None
    if mastery not in {"Slow", "Topple"}:
        return None
    if mastery == "Slow" and attack.damage <= 0:
        return None
    if attack.weapon_id is None or attack.weapon_name is None:
        return None
    return WeaponMasteryRequest(
        action_id=action_id,
        attacker_ref=attacker_ref,
        target_ref=target_ref,
        mastery=mastery,
        weapon_id=attack.weapon_id,
        weapon_name=attack.weapon_name,
        save_dc=(
            8 + attack.ability_modifier + attack.proficiency_bonus
            if mastery == "Topple"
            else None
        ),
    )


def open_weapon_mastery_decision(
    state: EncounterState,
    request: WeaponMasteryRequest,
    progress: EncounterProgress,
    *,
    continuation: DecisionContinuation | None = None,
) -> None:
    """Open the attacker's optional post-hit mastery decision."""

    parent = state.current_decision()
    frame = DecisionFrame(
        id=next_frame_id(state, prefix="weapon_mastery"),
        creature_ref=request.attacker_ref,
        kind="weapon_mastery",
        reason=request.mastery.casefold(),
        parent_frame_id=parent.id,
        parent_action_id=request.action_id,
        can_pass=True,
        request=request,
        continuation=continuation,
    )
    state.interrupts.decision_stack.append(frame)
    progress.events.append(
        create_event(
            state,
            "decision_opened",
            creature_ref=request.attacker_ref,
            frame_id=frame.id,
            action_id=request.action_id,
            data={
                "kind": "weapon_mastery",
                "mastery": request.mastery,
                "weapon_id": request.weapon_id,
                "target_ref": request.target_ref,
                "save_dc": request.save_dc,
            },
        )
    )
    progress.paused_for_decision = True


def weapon_mastery_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer using or declining the mastery carried by the current request."""

    decision = state.current_decision()
    request = _mastery_request(decision)
    mastery_id = request.mastery.casefold()
    return [
        EncounterAction(
            f"Use {request.mastery}",
            "use_weapon_mastery",
            id=f"{request.action_id}-mastery-{mastery_id}-use",
            creature_ref=request.attacker_ref,
            source_trigger_id=mastery_id,
        ),
        EncounterAction(
            f"Do not use {request.mastery}",
            "decline_weapon_mastery",
            id=f"{request.action_id}-mastery-{mastery_id}-decline",
            creature_ref=request.attacker_ref,
            source_trigger_id=mastery_id,
        ),
    ]


def apply_weapon_mastery_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Resolve an advertised mastery choice and its immediate rule effect."""

    if action.kind not in {"use_weapon_mastery", "decline_weapon_mastery"}:
        raise ValueError("Weapon Mastery must be used or declined.")
    request = _mastery_request(decision)
    progress = EncounterProgress()
    if action.kind == "use_weapon_mastery":
        if request.mastery == "Topple":
            _resolve_topple(state, request, progress, frame_id=decision.id)
        elif request.mastery == "Slow":
            _resolve_slow(state, request, progress, frame_id=decision.id)
        else:
            raise ValueError(f"Unsupported weapon mastery: {request.mastery}")
    else:
        progress.events.append(
            create_event(
                state,
                "weapon_mastery_resolved",
                creature_ref=request.attacker_ref,
                frame_id=decision.id,
                action_id=request.action_id,
                data={
                    "mastery": request.mastery,
                    "weapon_id": request.weapon_id,
                    "target_ref": request.target_ref,
                    "used": False,
                },
            )
        )
    return DecisionExecutionResult(progress, action.id, completed=True)


def resolve_weapon_mastery_automatically(
    state: EncounterState,
    request: WeaponMasteryRequest,
    progress: EncounterProgress,
) -> None:
    """Use a supported mastery in a scripted path that cannot suspend movement."""

    if request.mastery == "Topple":
        _resolve_topple(state, request, progress)
    elif request.mastery == "Slow":
        _resolve_slow(state, request, progress)
    else:
        raise ValueError(f"Unsupported automatic weapon mastery: {request.mastery}")


def _resolve_slow(
    state: EncounterState,
    request: WeaponMasteryRequest,
    progress: EncounterProgress,
    *,
    frame_id: str | None = None,
) -> None:
    progress.messages.extend(
        apply_encounter_effects(
            state,
            [
                EffectResult(
                    kind="start_ongoing_effect",
                    target_ref=request.target_ref,
                    data={
                        "source_ref": request.attacker_ref,
                        "source_label": request.weapon_name,
                        "source_kind": EffectSourceKind.FEATURE.value,
                        "definition_id": "weapon_mastery_slow",
                        "effect_kind": "generic",
                        "polarity": "harmful",
                        "dispellable": False,
                    },
                    rule_effects=(SpeedAdjustment(-10),),
                    effect_label="Slow",
                    duration=UntilTurnStart(request.attacker_ref),
                )
            ],
            origin_id=f"{request.action_id}:weapon_mastery:slow",
        )
    )
    target_label = creature_label(state, request.target_ref)
    progress.messages.append(
        ("system", f"{target_label}'s Speed is reduced by 10 feet by Slow.")
    )
    progress.events.append(
        create_event(
            state,
            "weapon_mastery_resolved",
            creature_ref=request.attacker_ref,
            frame_id=frame_id,
            action_id=request.action_id,
            data={
                "mastery": request.mastery,
                "weapon_id": request.weapon_id,
                "target_ref": request.target_ref,
                "used": True,
                "speed_reduction_feet": 10,
                "expires_at": "start_of_attacker_next_turn",
            },
        )
    )


def _resolve_topple(
    state: EncounterState,
    request: WeaponMasteryRequest,
    progress: EncounterProgress,
    *,
    frame_id: str | None = None,
) -> None:
    if request.save_dc is None:
        raise ValueError("Topple requires a saving throw DC.")
    resolve_effect_lifecycle_event(
        state,
        "target_forces_saving_throw",
        actor_ref=request.attacker_ref,
        target_ref=request.target_ref,
        progress=progress,
    )
    target = state.creatures[request.target_ref].creature
    rules = roll_modifiers(
        state,
        request.target_ref,
        "saving_throw",
        ability="constitution",
    )
    automatic_failures = automatic_save_failure_provider_ids_for(
        state,
        request.target_ref,
        "constitution",
    )
    save = resolve_saving_throw(
        target,
        "constitution",
        request.save_dc,
        mode=(
            "advantage"
            if has_condition_save_advantage(
                state,
                request.target_ref,
                (Condition.PRONE.value,),
            )
            else "normal"
        ),
        sourced_modifier_override=resolve_saving_throw_modifier(
            state,
            request.target_ref,
            rules,
        ),
        sourced_mode_override=rules.mode,
        roller=state.dice.roll_die,
        automatic_failure_reasons=automatic_failures,
    )
    target_label = creature_label(state, request.target_ref)
    condition_applied = False
    if save.check.success:
        progress.messages.append(
            (
                "system",
                f"{target_label} resists Topple "
                f"(Constitution {save.check.roll.total} vs DC {request.save_dc}).",
            )
        )
    else:
        application = apply_condition(
            state,
            build_applied_condition(
                condition=Condition.PRONE,
                source_ref=request.attacker_ref,
                source_label=request.weapon_name,
                target_ref=request.target_ref,
                source_kind=EffectSourceKind.FEATURE,
                definition_id="topple",
                origin_id=request.action_id,
            ),
        )
        condition_applied = application.accepted
        if condition_applied:
            progress.messages.append(
                (
                    "system",
                    f"{target_label} fails Topple "
                    f"(Constitution {save.check.roll.total} vs DC {request.save_dc}) "
                    "and falls prone.",
                )
            )
        else:
            progress.messages.append(
                ("system", f"{target_label} is immune to being prone.")
            )
    progress.events.append(
        create_event(
            state,
            "weapon_mastery_resolved",
            creature_ref=request.attacker_ref,
            frame_id=frame_id,
            action_id=request.action_id,
            data={
                "mastery": request.mastery,
                "weapon_id": request.weapon_id,
                "target_ref": request.target_ref,
                "used": True,
                "save_ability": "constitution",
                "save_dc": request.save_dc,
                "save_roll": save.check.roll.total,
                "save_die": save.check.roll.selected,
                "save_succeeded": save.check.success,
                "automatic_failure_reasons": list(automatic_failures),
                "condition_applied": condition_applied,
            },
        )
    )


def _mastery_request(decision: DecisionFrame) -> WeaponMasteryRequest:
    if not isinstance(decision.request, WeaponMasteryRequest):
        raise TypeError("Weapon Mastery decision requires its typed request.")
    return decision.request
