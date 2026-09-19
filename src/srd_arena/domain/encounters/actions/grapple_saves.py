"""Resolve the target-owned saving-throw choice for a Grapple attempt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from srd_arena.domain.effects.application import condition_from_effect_with_origin
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.rolls.saving_throws import Ability, resolve_saving_throw

from ..effect_lifecycle.lifecycle_events import resolve_effect_lifecycle_event
from ..effect_lifecycle.roll_usage import resolve_saving_throw_modifier
from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import DecisionFrame, GrappleSaveRequest
from ..encounter_models.resolution import DecisionExecutionResult, EncounterProgress
from ..grappling_state import apply_grapple
from ..rule_queries.defenses import has_condition_save_advantage
from ..rule_queries.rolls import roll_modifiers
from ..state_combat import automatic_save_failure_provider_ids_for
from ..state_runtime import create_event, creature_label

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature

    from ..encounter import EncounterState

GrappleSaveChoice = Literal["strength", "dexterity", "fail"]


def grapple_save_request(decision: DecisionFrame) -> GrappleSaveRequest:
    """Return the typed grapple request carried by a decision frame."""

    if not isinstance(decision.request, GrappleSaveRequest):
        raise TypeError("Grapple save decision requires a GrappleSaveRequest.")
    return decision.request


def grapple_save_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer Strength, Dexterity, and voluntary failure to the grapple target."""

    decision = state.current_decision()
    request = grapple_save_request(decision)
    return [
        EncounterAction(
            "Strength saving throw",
            "grapple_save",
            "strength",
            id=f"{request.action_id}-grapple-save-strength",
            creature_ref=request.target_ref,
        ),
        EncounterAction(
            "Dexterity saving throw",
            "grapple_save",
            "dexterity",
            id=f"{request.action_id}-grapple-save-dexterity",
            creature_ref=request.target_ref,
        ),
        EncounterAction(
            "Fail saving throw",
            "grapple_save",
            "fail",
            id=f"{request.action_id}-grapple-save-fail",
            creature_ref=request.target_ref,
        ),
    ]


def preferred_grapple_save_ability(
    creature: Creature,
) -> Literal["strength", "dexterity"]:
    """Choose the stronger intrinsic grapple save for a scripted creature."""

    strength = _saving_throw_bonus(creature, "strength")
    dexterity = _saving_throw_bonus(creature, "dexterity")
    return "strength" if strength >= dexterity else "dexterity"


def apply_grapple_save_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Resolve a grapple target's advertised saving-throw choice."""

    if action.kind != "grapple_save" or action.value not in {
        "strength",
        "dexterity",
        "fail",
    }:
        raise ValueError("A grapple save requires Strength, Dexterity, or failure.")
    request = grapple_save_request(decision)
    progress = EncounterProgress()
    resolve_grapple_save(
        state,
        request,
        cast(GrappleSaveChoice, action.value),
        progress,
        frame_id=decision.id,
    )
    return DecisionExecutionResult(
        progress=progress,
        action_id=request.action_id,
        completed=True,
    )


def resolve_grapple_save(
    state: EncounterState,
    request: GrappleSaveRequest,
    choice: GrappleSaveChoice,
    progress: EncounterProgress,
    *,
    frame_id: str | None = None,
) -> None:
    """Resolve one chosen save and finish its originating Grapple attempt."""

    resolve_effect_lifecycle_event(
        state,
        "target_forces_saving_throw",
        actor_ref=request.grappler_ref,
        target_ref=request.target_ref,
        progress=progress,
    )
    target = state.creatures[request.target_ref].creature
    grappler = state.creatures[request.grappler_ref].creature
    roll_die = state.dice.roll_die
    voluntarily_failed = choice == "fail"
    save = None
    if voluntarily_failed:
        success = False
        automatic_failure_reasons: tuple[str, ...] = ()
    else:
        ability = cast(Ability, choice)
        rules = roll_modifiers(
            state,
            request.target_ref,
            "saving_throw",
            ability=ability,
        )
        automatic_failure_reasons = automatic_save_failure_provider_ids_for(
            state,
            request.target_ref,
            ability,
        )
        save = resolve_saving_throw(
            target,
            ability,
            request.save_dc,
            mode=(
                "advantage"
                if has_condition_save_advantage(
                    state,
                    request.target_ref,
                    (Condition.GRAPPLED.value,),
                )
                else "normal"
            ),
            sourced_modifier_override=resolve_saving_throw_modifier(
                state,
                request.target_ref,
                rules,
            ),
            sourced_mode_override=rules.mode,
            roller=roll_die,
            automatic_failure_reasons=automatic_failure_reasons,
        )
        success = save.check.success

    target_label = creature_label(state, request.target_ref)
    grapple_succeeded = False
    event_data: dict[str, object] = {
        "target_ref": request.target_ref,
        "target_label": target_label,
        "save_ability": None if voluntarily_failed else choice,
        "save_dc": request.save_dc,
        "voluntarily_failed": voluntarily_failed,
        "automatic_failure_reasons": list(automatic_failure_reasons),
        "save_succeeded": success,
    }
    if save is not None:
        event_data.update(
            {
                "save_roll": save.check.roll.total,
                "save_die": save.check.roll.selected,
                "save_roll_detail": {
                    "dice": list(save.check.roll.dice),
                    "mode": save.check.roll.mode,
                    "modifier": save.modifiers.total,
                    "total": save.check.roll.total,
                },
            }
        )

    if not success:
        application = apply_grapple(
            state,
            condition_from_effect_with_origin(
                EffectResult(
                    kind="apply_condition",
                    target_ref=request.target_ref,
                    data={
                        "condition": "grappled",
                        "source_ref": request.grappler_ref,
                        "source_label": grappler.name,
                        "source_kind": "action",
                        "definition_id": "grapple",
                        "metadata": {"escape_dc": request.save_dc},
                    },
                ),
                origin_id=request.action_id,
            ),
        )
        if application.accepted:
            grapple_succeeded = True
            progress.messages.append(
                ("system", f"{grappler.name} grapples {target_label}.")
            )
            progress.messages.append(("system", f"{target_label} is grappled."))
        else:
            event_data["condition_applied"] = False
            progress.messages.append(
                ("system", f"{target_label} is immune to being grappled.")
            )
    else:
        progress.messages.append(
            ("system", f"{target_label} resists {grappler.name}'s grapple.")
        )

    event_data["success"] = grapple_succeeded

    progress.events.append(
        create_event(
            state,
            "grapple_resolved",
            creature_ref=request.grappler_ref,
            frame_id=frame_id,
            action_id=request.action_id,
            data=event_data,
        )
    )
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=request.grappler_ref,
            frame_id=frame_id,
            action_id=request.action_id,
            data={
                "kind": "grapple",
                "success": grapple_succeeded,
                "target_ref": request.target_ref,
            },
        )
    )


def _saving_throw_bonus(creature: Creature, ability: Ability) -> int:
    explicit = creature.explicit_saving_throw_bonus(ability)
    if explicit is not None:
        return explicit
    bonus = creature.get_modifier(creature.saving_throw_ability_score(ability))
    if creature.is_saving_throw_proficient(ability):
        bonus += creature.saving_throw_proficiency_bonus
    return bonus
