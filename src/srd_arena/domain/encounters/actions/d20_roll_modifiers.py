"""Offer optional feature-driven changes before addressed D20 rolls resolve."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import AttackResolution, SavingThrowResolution
from srd_arena.domain.creatures.feature_rules import LUCKY_FEATURE_ID, has_lucky
from srd_arena.domain.creatures.stat_block_actions import SavingThrowActionDefinition
from srd_arena.domain.rolls.dice import D20RollMode, combine_roll_modes
from srd_arena.domain.rolls.occurrences import (
    attack_roll_occurrence_id,
    spell_attack_occurrence_id,
    spell_save_occurrence_id,
    stat_block_save_occurrence_id,
)
from srd_arena.domain.spells import Spell

from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import (
    D20RollModifierRequest,
    D20RollOccurrence,
    DecisionContinuation,
    DecisionFrame,
    LuckyRollOption,
    PendingD20RollModifiers,
)
from ..encounter_models.resolution import DecisionExecutionResult, EncounterProgress
from ..state_runtime import create_event, creature_label, next_frame_id
from .stat_block_runtime.targets import stat_block_target_refs

if TYPE_CHECKING:
    from ..encounter import EncounterState


def action_d20_occurrences(
    state: EncounterState,
    action: EncounterAction,
    actor_ref: str,
) -> tuple[D20RollOccurrence, ...]:
    """Describe immediate attack or stat-block save rolls made by an action."""

    if action.kind == "attack" and isinstance(action.value, str):
        return (
            D20RollOccurrence(
                attack_roll_occurrence_id(),
                "attack_roll",
                actor_ref,
                action.value,
                f"Attack against {creature_label(state, action.value)}",
            ),
        )
    if action.kind != "stat_block":
        return ()
    actor = state.creatures[actor_ref].creature
    definition = actor.stat_block_actions.get(action.preferred_attack_name or "")
    if not isinstance(definition, SavingThrowActionDefinition) or not isinstance(
        action.value, (str, tuple)
    ):
        return ()
    return tuple(
        D20RollOccurrence(
            stat_block_save_occurrence_id(index),
            "saving_throw",
            target_ref,
            target_ref,
            f"Saving throw against {definition.name}",
        )
        for index, target_ref in enumerate(
            stat_block_target_refs(state, actor_ref, action.value, definition),
            start=1,
        )
    )


def spell_d20_occurrences(
    state: EncounterState,
    spell: Spell,
    caster_ref: str,
    target_refs: tuple[str, ...],
) -> tuple[D20RollOccurrence, ...]:
    """Describe each primary spell attack or saving throw in target order."""

    if spell.definition is None:
        return ()
    resolution = spell.definition.resolution
    if isinstance(resolution, AttackResolution):
        return tuple(
            D20RollOccurrence(
                spell_attack_occurrence_id(index),
                "attack_roll",
                caster_ref,
                target_ref,
                f"{spell.name} attack against {creature_label(state, target_ref)}",
            )
            for index, target_ref in enumerate(target_refs, start=1)
        )
    if isinstance(resolution, SavingThrowResolution):
        return tuple(
            D20RollOccurrence(
                spell_save_occurrence_id(index),
                "saving_throw",
                target_ref,
                target_ref,
                f"Saving throw against {spell.name}",
            )
            for index, target_ref in enumerate(target_refs, start=1)
        )
    return ()


def open_d20_roll_modifier_decision(
    state: EncounterState,
    occurrences: tuple[D20RollOccurrence, ...],
    *,
    action_id: str,
    continuation: DecisionContinuation,
    progress: EncounterProgress,
) -> bool:
    """Suspend an action when Lucky can modify one of its future D20 rolls."""

    options = _lucky_options(state, occurrences)
    if not options:
        return False
    pending = PendingD20RollModifiers(action_id=action_id, options=options)
    current = pending.current_option
    frame_id = next_frame_id(state, prefix="d20_roll")
    state.interrupts.decision_stack.append(
        DecisionFrame(
            id=frame_id,
            creature_ref=current.owner_ref,
            kind="d20_roll_modifier",
            reason=current.occurrence.label,
            request=D20RollModifierRequest(pending),
            continuation=continuation,
        )
    )
    progress.paused_for_decision = True
    progress.events.append(
        create_event(
            state,
            "decision_opened",
            creature_ref=current.owner_ref,
            frame_id=frame_id,
            action_id=action_id,
            data=_decision_event_data(current),
        )
    )
    return True


def d20_roll_modifier_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer declining or spending a Luck Point for the current roll."""

    decision = state.current_decision()
    request = _modifier_request(decision)
    option = request.pending.current_option
    actions = [
        EncounterAction(
            "Do not spend a Luck Point",
            "decline_d20_modifier",
            id=f"{decision.id}-decline-{request.pending.option_index}",
            creature_ref=option.owner_ref,
        )
    ]
    owner = state.creatures[option.owner_ref].creature
    if owner.feature_uses_remaining.get(LUCKY_FEATURE_ID, 0) > 0:
        effect = (
            "gain Advantage" if option.mode == "advantage" else "impose Disadvantage"
        )
        actions.append(
            EncounterAction(
                f"Spend a Luck Point to {effect}",
                "use_lucky",
                id=f"{decision.id}-use-lucky-{request.pending.option_index}",
                creature_ref=option.owner_ref,
            )
        )
    return actions


def apply_d20_roll_modifier_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Apply one Lucky choice and advance or complete its roll plan."""

    if action.kind not in {"decline_d20_modifier", "use_lucky"}:
        raise ValueError("D20 roll modifier choice must decline or use Lucky.")
    request = _modifier_request(decision)
    pending = request.pending
    option = pending.current_option
    progress = EncounterProgress()
    used = action.kind == "use_lucky"
    if used:
        owner = state.creatures[option.owner_ref].creature
        owner.spend_feature_use(LUCKY_FEATURE_ID)
        pending.selected_modes.setdefault(option.occurrence.id, []).append(option.mode)

    progress.events.append(
        create_event(
            state,
            "d20_roll_modifier_resolved",
            creature_ref=option.owner_ref,
            frame_id=decision.id,
            action_id=pending.action_id,
            data={
                **_decision_event_data(option),
                "used": used,
                "uses_remaining": state.creatures[
                    option.owner_ref
                ].creature.feature_uses_remaining.get(LUCKY_FEATURE_ID, 0),
            },
        )
    )
    if used:
        progress.messages.append(
            (
                "system",
                f"{creature_label(state, option.owner_ref)} spends a Luck Point "
                f"to {'gain Advantage' if option.mode == 'advantage' else 'impose Disadvantage'}.",
            )
        )

    pending.option_index += 1
    while pending.option_index < len(pending.options):
        candidate = pending.current_option
        owner = state.creatures[candidate.owner_ref].creature
        if owner.feature_uses_remaining.get(LUCKY_FEATURE_ID, 0) > 0:
            break
        pending.option_index += 1
    if pending.option_index < len(pending.options):
        next_option = pending.current_option
        decision.creature_ref = next_option.owner_ref
        decision.reason = next_option.occurrence.label
        progress.paused_for_decision = True
        progress.events.append(
            create_event(
                state,
                "decision_updated",
                creature_ref=next_option.owner_ref,
                frame_id=decision.id,
                action_id=pending.action_id,
                data=_decision_event_data(next_option),
            )
        )
        return DecisionExecutionResult(progress, action.id, completed=False)

    activate_d20_roll_modes(
        state,
        pending.action_id,
        {
            occurrence_id: combine_roll_modes(*modes)
            for occurrence_id, modes in pending.selected_modes.items()
        },
    )
    return DecisionExecutionResult(progress, action.id, completed=True)


def activate_d20_roll_modes(
    state: EncounterState,
    action_id: str,
    modes: dict[str, D20RollMode],
) -> None:
    """Install addressed roll-mode contributions for one resumed action."""

    state.active_d20_action_id = action_id
    state.active_d20_roll_modes = dict(modes)


def consume_d20_roll_mode(
    state: EncounterState,
    action_id: str,
    occurrence_id: str,
) -> D20RollMode:
    """Consume the optional mode addressed to one exact roll occurrence."""

    if state.active_d20_action_id != action_id:
        return "normal"
    return state.active_d20_roll_modes.pop(occurrence_id, "normal")


def clear_d20_roll_modes(state: EncounterState, action_id: str) -> None:
    """Discard unused addressed modifiers when their action has completed."""

    if state.active_d20_action_id != action_id:
        return
    state.active_d20_action_id = None
    state.active_d20_roll_modes.clear()


def _lucky_options(
    state: EncounterState,
    occurrences: tuple[D20RollOccurrence, ...],
) -> tuple[LuckyRollOption, ...]:
    options: list[LuckyRollOption] = []
    for occurrence in occurrences:
        roller = state.creatures[occurrence.roller_ref].creature
        if (
            has_lucky(roller)
            and roller.feature_uses_remaining.get(LUCKY_FEATURE_ID, 0) > 0
        ):
            options.append(
                LuckyRollOption(occurrence.roller_ref, occurrence, "advantage")
            )
        if (
            occurrence.kind == "attack_roll"
            and occurrence.target_ref is not None
            and occurrence.target_ref != occurrence.roller_ref
        ):
            target = state.creatures[occurrence.target_ref].creature
            if (
                has_lucky(target)
                and target.feature_uses_remaining.get(LUCKY_FEATURE_ID, 0) > 0
            ):
                options.append(
                    LuckyRollOption(
                        occurrence.target_ref,
                        occurrence,
                        "disadvantage",
                    )
                )
    return tuple(options)


def _modifier_request(decision: DecisionFrame) -> D20RollModifierRequest:
    if not isinstance(decision.request, D20RollModifierRequest):
        raise TypeError("D20 roll decision requires a modifier request.")
    return decision.request


def _decision_event_data(option: LuckyRollOption) -> dict[str, object]:
    return {
        "kind": "d20_roll_modifier",
        "feature_id": LUCKY_FEATURE_ID,
        "roll_occurrence_id": option.occurrence.id,
        "roll_kind": option.occurrence.kind,
        "roller_ref": option.occurrence.roller_ref,
        "target_ref": option.occurrence.target_ref,
        "mode": option.mode,
    }
