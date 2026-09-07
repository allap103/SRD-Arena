"""Coordinate the readable, high-level flow of an encounter.

The orchestrator owns decisions, continuations, and the transition between
actions and turns. It deliberately delegates action mechanics, reaction
resolution, and turn-boundary work to their focused functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .actions.d20_roll_modifiers import apply_d20_roll_modifier_action
from .actions.forced_movement_choices import apply_forced_movement_action
from .actions.grapple_saves import apply_grapple_save_action
from .actions.initiative_swaps import apply_initiative_swap_action
from .actions.options import decision_actions
from .actions.reckless_attack import apply_reckless_attack_action
from .actions.weapon_mastery import apply_weapon_mastery_action
from .continuations import ContinuationRunner
from .creature_control import available_creature_actions, execute_creature_action
from .encounter_models.actions import (
    CreatureRef,
    EncounterAction,
)
from .encounter_models.decisions import DecisionFrame
from .encounter_models.resolution import (
    ActionExecutionOutcome,
    DecisionExecutionResult,
    EncounterProgress,
)
from .participants import creature_controller
from .reaction_runtime.damage_rerolls import apply_damage_reroll_action
from .reaction_runtime.opportunity_execution import apply_reaction_action
from .reaction_runtime.parry import apply_parry_action
from .state_runtime import merge_progress
from .turn_lifecycle import (
    active_turn_creature,
    advance_turn,
    encounter_is_complete,
    maybe_reset_reactions,
    movement_budget_for_turn,
    skip_defeated_turn,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class EncounterOrchestrator:
    """Drive an encounter until it finishes or requires a controller decision."""

    def submit(
        self,
        state: EncounterState,
        action: EncounterAction,
    ) -> EncounterProgress:
        """Apply one externally selected action and continue as far as possible.

        Actions cannot be submitted on behalf of a different decision actor.

        >>> from unittest.mock import Mock
        >>> decision = DecisionFrame("turn-hero", "hero", "turn", "active_turn")
        >>> state = Mock()
        >>> state.current_decision.return_value = decision
        >>> action = EncounterAction("Wait", "wait", id="wait", creature_ref="goblin")
        >>> EncounterOrchestrator().submit(state, action)
        Traceback (most recent call last):
        ...
        ValueError: Action 'wait' belongs to 'goblin', not current decision actor 'hero'.
        """
        decision = state.current_decision()
        if action.creature_ref != decision.creature_ref:
            raise ValueError(
                f"Action '{action.id}' belongs to '{action.creature_ref}', "
                f"not current decision actor '{decision.creature_ref}'."
            )
        if creature_controller(state, decision.creature_ref) != "external":
            raise RuntimeError(
                "External action requested for a scripted-controlled creature."
            )

        return self._apply_current_action(state, action, decision)

    def _apply_current_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        """Dispatch either a specialized choice or an ordinary selected action."""

        if decision.kind in {
            "reroll_dice",
            "reaction",
            "parry",
            "grapple_save",
            "forced_movement",
            "initiative_swap",
            "d20_roll_modifier",
            "reckless_attack",
            "weapon_mastery",
        }:
            return self._apply_decision_action(state, action, decision)
        return self._apply_selected_action(state, action, decision)

    def _apply_decision_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        """Resolve one specialized decision for either controller type."""

        if decision.kind == "reroll_dice":
            result = apply_damage_reroll_action(
                state,
                action,
                decision,
            )
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "reaction":
            result = apply_reaction_action(
                state,
                action,
                decision,
            )
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "parry":
            result = apply_parry_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "grapple_save":
            result = apply_grapple_save_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "forced_movement":
            result = apply_forced_movement_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "initiative_swap":
            result = apply_initiative_swap_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "d20_roll_modifier":
            result = apply_d20_roll_modifier_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "reckless_attack":
            result = apply_reckless_attack_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "weapon_mastery":
            result = apply_weapon_mastery_action(state, action, decision)
            return self._finish_decision_execution(state, decision, result)
        raise ValueError(f"Unsupported specialized decision: {decision.kind}")

    def advance(self, state: EncounterState) -> EncounterProgress:
        """Resolve scripted actions until input or completion stops execution.

        An already completed encounter returns without selecting another action.

        >>> from unittest.mock import Mock
        >>> state = Mock(interrupts=Mock(decision_stack=[]))
        >>> from unittest.mock import patch
        >>> with patch(
        ...     "srd_arena.domain.encounters.orchestration.encounter_is_complete",
        ...     return_value=True,
        ... ):
        ...     completed = EncounterOrchestrator().advance(state).completed
        >>> completed
        True
        """
        return self._advance(state, stop_after_action=False)

    def advance_one_action(self, state: EncounterState) -> EncounterProgress:
        """Resolve at most one scripted action and return its events immediately.

        No delay is introduced here; presentation clients decide when to call
        this operation again.

        >>> from unittest.mock import Mock
        >>> state = Mock(interrupts=Mock(decision_stack=[]))
        >>> from unittest.mock import patch
        >>> with patch(
        ...     "srd_arena.domain.encounters.orchestration.encounter_is_complete",
        ...     return_value=True,
        ... ):
        ...     completed = EncounterOrchestrator().advance_one_action(state).completed
        >>> completed
        True
        """
        return self._advance(state, stop_after_action=True)

    def _advance(
        self,
        state: EncounterState,
        *,
        stop_after_action: bool,
    ) -> EncounterProgress:
        """Resolve scripted actions with caller-selected execution granularity."""

        progress = EncounterProgress()
        automatic_action_resolved = False
        while True:
            self._record_completion(state, progress)
            if progress.completed:
                break
            if state.interrupts.decision_stack:
                decision = state.current_decision()
                if creature_controller(state, decision.creature_ref) == "external":
                    progress.paused_for_decision = True
                    break
                if stop_after_action and automatic_action_resolved:
                    break
                actions = decision_actions(state)
                selected_action = state._action_selectors[
                    decision.creature_ref
                ].select_action(
                    state,
                    decision.creature_ref,
                    tuple(actions),
                )
                if selected_action is None:
                    raise RuntimeError(
                        "A scripted controller declined its required decision."
                    )
                decision_progress = self._apply_current_action(
                    state,
                    selected_action,
                    decision,
                )
                if (
                    state.interrupts.decision_stack
                    and creature_controller(
                        state,
                        state.current_decision().creature_ref,
                    )
                    == "scripted"
                ):
                    decision_progress.paused_for_decision = False
                merge_progress(state, progress, decision_progress)
                automatic_action_resolved = True
                if progress.completed or stop_after_action:
                    break
                continue

            creature_ref = active_turn_creature(state)
            if not state.creatures[creature_ref].is_alive:
                skip_defeated_turn(state, progress)
                maybe_reset_reactions(state)
                continue
            if stop_after_action and automatic_action_resolved:
                break
            selected_action = state._action_selectors[creature_ref].select_action(
                state,
                creature_ref,
                tuple(
                    available_creature_actions(
                        state,
                        creature_ref,
                        include_attack_alternatives=True,
                    )
                ),
            )
            if selected_action is None:
                progress.paused_for_decision = True
                break

            completed_turn, actor_progress = self._run_creature_turn(
                state,
                creature_ref,
                initial_action=selected_action,
                stop_after_action=stop_after_action,
            )
            automatic_action_resolved = True
            merge_progress(state, progress, actor_progress)
            if progress.completed:
                break
            if progress.paused_for_decision:
                if (
                    not stop_after_action
                    and state.interrupts.decision_stack
                    and creature_controller(
                        state,
                        state.current_decision().creature_ref,
                    )
                    == "scripted"
                ):
                    progress.paused_for_decision = False
                    continue
                break
            if completed_turn:
                self._finish_turn(state, creature_ref, progress)
                self._record_completion(state, progress)
                if progress.completed:
                    break
        return progress

    def _finish_decision_execution(
        self,
        state: EncounterState,
        decision: DecisionFrame,
        result: DecisionExecutionResult,
    ) -> EncounterProgress:
        progress = result.progress
        if result.completed:
            ContinuationRunner().complete_decision(
                state,
                decision,
                action_id=result.action_id,
                progress=progress,
            )
        self._record_completion(state, progress)
        return progress

    def _record_completion(
        self,
        state: EncounterState,
        progress: EncounterProgress,
    ) -> None:
        if not progress.completed and not state.interrupts.decision_stack:
            progress.completed = encounter_is_complete(state)

    def _finish_turn(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        progress: EncounterProgress,
    ) -> None:
        if state.creatures[creature_ref].is_alive:
            advance_turn(state, progress)
        else:
            skip_defeated_turn(state, progress)
        maybe_reset_reactions(state)

    def _apply_selected_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        result = execute_creature_action(state, action, decision)
        progress = result.progress
        self._record_completion(state, progress)
        if progress.completed:
            return progress
        if result.outcome is not ActionExecutionOutcome.END_TURN:
            return progress
        self._finish_turn(state, decision.creature_ref, progress)
        return progress

    def _run_creature_turn(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        *,
        initial_action: EncounterAction | None = None,
        stop_after_action: bool = False,
    ) -> tuple[bool, EncounterProgress]:
        actor = state.creatures[creature_ref]
        progress = EncounterProgress()
        if not actor.is_alive:
            return True, progress
        if actor.movement_remaining is None:
            actor.movement_remaining = movement_budget_for_turn(state, creature_ref)

        selector = state._action_selectors[creature_ref]
        action = initial_action or selector.select_action(
            state,
            creature_ref,
            tuple(
                available_creature_actions(
                    state,
                    creature_ref,
                    include_attack_alternatives=True,
                )
            ),
        )
        if action is None:
            return False, progress

        while actor.is_alive:
            result = execute_creature_action(
                state,
                action,
                DecisionFrame(
                    id=f"turn-{creature_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    kind="turn",
                    reason="scripted_turn",
                ),
            )
            self._record_completion(state, result.progress)
            merge_progress(state, progress, result.progress)
            if progress.completed:
                return True, progress
            if result.outcome is ActionExecutionOutcome.PAUSE_FOR_DECISION:
                return False, progress
            if result.outcome is ActionExecutionOutcome.END_TURN or (
                action.kind == "attack" and actor.attacks_remaining == 0
            ):
                return True, progress
            if stop_after_action:
                return False, progress

            action = selector.select_action(
                state,
                creature_ref,
                tuple(
                    available_creature_actions(
                        state,
                        creature_ref,
                        include_attack_alternatives=True,
                    )
                ),
            )
            if action is None:
                return False, progress
        return True, progress
