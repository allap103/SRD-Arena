"""Discover and execute Hide and Search actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import (
    AppliedCondition,
    Condition,
    build_applied_condition,
)
from srd_arena.domain.effects.runtime import (
    EffectPolarity,
    EffectSource,
    EffectSourceKind,
    EndEventRule,
    OngoingEffect,
    OngoingEffectLifecycle,
    RuntimeStateIdentity,
)
from srd_arena.domain.rolls.dice import resolve_d20

from ...attack_economy import clear_attack_action, consume_action
from ...condition_state import apply_condition
from ...effect_lifecycle.removal import _remove_effect_tree
from ...encounter_models.actions import ActionCost, CreatureRef, EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ...participants import creatures_are_opponents
from ...rule_queries.obstructions import cover_between
from ...rule_queries.rolls import roll_modifiers
from ...rule_queries.visibility import (
    creature_can_see_creature,
    creature_is_heavily_obscured,
)
from ...state_runtime import create_event, next_runtime_origin_id
from ...terrain import CoverDegree
from ..eligibility_rules.models import EligibilityFailure
from ..rejections import reject_action

if TYPE_CHECKING:
    from ...encounter import EncounterState
    from ...encounter_models.decisions import DecisionFrame


HIDE_DIFFICULTY_CLASS = 15


def hide_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Return the universal Hide action and relevant Search actions."""

    actions = [
        EncounterAction(
            "Hide",
            "hide",
            id=f"{creature_ref}-hide",
            creature_ref=creature_ref,
            cost=ActionCost(action=1),
        )
    ]
    for target_ref, hidden in _hidden_opponents(state, creature_ref):
        actions.append(
            EncounterAction(
                f"Search for {state.creatures[target_ref].creature.name}",
                "search_hidden",
                target_ref,
                id=f"{creature_ref}-search-hidden-{target_ref.replace(':', '-')}",
                creature_ref=creature_ref,
                cost=ActionCost(action=1),
                preferred_attack_name=hidden.identity.source.label,
            )
        )
    return actions


def hide_eligibility_failure(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> EligibilityFailure | None:
    """Return why the creature cannot currently attempt to Hide."""

    opponents = tuple(
        opponent_ref
        for opponent_ref, opponent in state.creatures.items()
        if opponent.is_alive
        and creatures_are_opponents(state, creature_ref, opponent_ref)
    )
    concealed_by_obscuration = creature_is_heavily_obscured(state, creature_ref)
    concealed_by_cover = bool(opponents) and all(
        cover_between(state, opponent_ref, creature_ref).degree.rank
        >= CoverDegree.THREE_QUARTERS.rank
        for opponent_ref in opponents
    )
    if not concealed_by_obscuration and not concealed_by_cover:
        return EligibilityFailure(
            "hide.concealment_required",
            "Hide requires Heavy Obscurement, Three-Quarters Cover, or Total Cover.",
        )
    visible_to = tuple(
        opponent_ref
        for opponent_ref in opponents
        if creature_can_see_creature(state, opponent_ref, creature_ref)
    )
    if visible_to:
        return EligibilityFailure(
            "hide.visible_to_enemy",
            "Hide requires being outside every enemy's line of sight.",
        )
    return None


def execute_hiding_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Execute a recognized Hide or Search action."""

    if action.kind == "hide":
        _execute_hide(state, action, decision, progress, action_id)
        return True
    if action.kind == "search_hidden":
        _execute_search(state, action, decision, progress, action_id)
        return True
    return False


def _execute_hide(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = decision.creature_ref
    creature = state.creatures[creature_ref].creature
    _spend_standard_action(state, action)
    roll_rules = roll_modifiers(
        state,
        creature_ref,
        "ability_check",
        ability="dexterity",
    )
    modifier = creature.skill_check_bonus("dexterity", "stealth")
    roll = resolve_d20(
        modifier=modifier + roll_rules.resolve_modifier(state.dice.roll_die),
        mode=roll_rules.mode,
        roller=state.dice.roll_die,
    )
    success = roll.total >= HIDE_DIFFICULTY_CLASS
    effect_id: str | None = None
    if success:
        effect_id = next_runtime_origin_id(state)
        source = EffectSource(
            EffectSourceKind.ACTION,
            "hide",
            applied_by_ref=creature_ref,
            label="Hide",
            origin_id=action_id,
        )
        state.ongoing_effects.append(
            OngoingEffect(
                identity=RuntimeStateIdentity(effect_id, source),
                target_refs=(creature_ref,),
                polarity=EffectPolarity.BENEFICIAL,
                label="Hidden",
                lifecycle=OngoingEffectLifecycle(
                    end_events=(
                        EndEventRule("target_makes_attack", "target"),
                        EndEventRule("target_casts_verbal_spell", "target"),
                    )
                ),
            )
        )
        application = apply_condition(
            state,
            build_applied_condition(
                condition=Condition.INVISIBLE,
                source_ref=creature_ref,
                source_label="Hide",
                target_ref=creature_ref,
                source_kind=EffectSourceKind.ACTION,
                definition_id="hide",
                origin_id=action_id,
                parent_id=effect_id,
                root_id=effect_id,
                metadata={"hidden": True, "stealth_total": roll.total},
            ),
        )
        if not application.accepted:
            effect = next(
                candidate
                for candidate in state.ongoing_effects
                if candidate.identity.id == effect_id
            )
            _remove_effect_tree(state, effect)
            effect_id = None
            success = False
    progress.messages.append(
        (
            "system",
            f"{creature.name} {'hides' if success else 'fails to hide'} "
            f"(Dexterity (Stealth) {roll.total} vs DC {HIDE_DIFFICULTY_CLASS}).",
        )
    )
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "hide",
                "dc": HIDE_DIFFICULTY_CLASS,
                "success": success,
                "effect_id": effect_id,
                "roll": roll.total,
                "roll_detail": {
                    "dice": list(roll.dice),
                    "mode": roll.mode,
                    "modifier": roll.modifier,
                    "total": roll.total,
                },
            },
        )
    )


def _execute_search(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    actor_ref = decision.creature_ref
    actor = state.creatures[actor_ref].creature
    hidden = (
        _hidden_condition(state, action.value)
        if isinstance(action.value, str)
        else None
    )
    if hidden is None:
        reject_action(
            state,
            progress,
            actor_ref=actor_ref,
            action_id=action_id,
            action_kind=action.kind,
            message="That creature is no longer hidden.",
            reason_code="hidden_target_unavailable",
        )
        return
    consume_action(state, allow_magic=False)
    clear_attack_action(state.active_creature_state)
    roll_rules = roll_modifiers(
        state,
        actor_ref,
        "ability_check",
        ability="wisdom",
    )
    modifier = actor.skill_check_bonus("wisdom", "perception")
    roll = resolve_d20(
        modifier=modifier + roll_rules.resolve_modifier(state.dice.roll_die),
        mode=roll_rules.mode,
        roller=state.dice.roll_die,
    )
    difficulty = hidden.metadata.get("stealth_total")
    if not isinstance(difficulty, int):
        raise RuntimeError("A hidden condition requires its Stealth total.")
    success = roll.total >= difficulty
    if success:
        parent_id = hidden.identity.parent_id
        effect = next(
            (
                candidate
                for candidate in state.ongoing_effects
                if candidate.identity.id == parent_id
            ),
            None,
        )
        if effect is not None:
            _remove_effect_tree(state, effect)
    target_name = state.creatures[hidden.target_ref].creature.name
    progress.messages.append(
        (
            "system",
            f"{actor.name} {'finds' if success else 'does not find'} {target_name} "
            f"(Wisdom (Perception) {roll.total} vs DC {difficulty}).",
        )
    )
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=actor_ref,
            action_id=action_id,
            data={
                "kind": "search_hidden",
                "target_ref": hidden.target_ref,
                "dc": difficulty,
                "success": success,
                "roll": roll.total,
                "roll_detail": {
                    "dice": list(roll.dice),
                    "mode": roll.mode,
                    "modifier": roll.modifier,
                    "total": roll.total,
                },
            },
        )
    )


def _spend_standard_action(state: EncounterState, action: EncounterAction) -> None:
    if action.cost.bonus_action:
        state.active_bonus_action_available = False
        return
    consume_action(state, allow_magic=False)
    clear_attack_action(state.active_creature_state)


def _hidden_opponents(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[tuple[CreatureRef, AppliedCondition], ...]:
    return tuple(
        (target_ref, hidden)
        for target_ref, target in state.creatures.items()
        if creatures_are_opponents(state, creature_ref, target_ref)
        and target.is_alive
        and cover_between(state, creature_ref, target_ref).has_line_of_effect
        and (hidden := _hidden_condition(state, target_ref)) is not None
    )


def _hidden_condition(
    state: EncounterState,
    target_ref: object,
) -> AppliedCondition | None:
    if not isinstance(target_ref, str):
        return None
    return next(
        (
            condition
            for condition in state.conditions_for(target_ref)
            if condition.condition is Condition.INVISIBLE
            and condition.metadata.get("hidden") is True
        ),
        None,
    )
