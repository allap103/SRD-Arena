"""Coordinate the readable, high-level flow of an encounter.

The orchestrator owns decisions, continuations, and the transition between
actions and turns. It deliberately delegates action mechanics, reaction
resolution, turn-boundary work, and rules calculations to their focused
services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .continuations import ContinuationRunner
from .models import (
    ActionExecutionOutcome,
    CreatureRef,
    DecisionExecutionResult,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class EncounterOrchestrator:
    """Drive an encounter until it finishes or requires a controller decision."""

    def __init__(
        self,
        continuation_runner: ContinuationRunner | None = None,
    ) -> None:
        self._continuation_runner = continuation_runner or ContinuationRunner()

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
        if state._creature_controller(decision.creature_ref) != "external":
            raise RuntimeError(
                "External action requested for a scripted-controlled creature."
            )

        if decision.kind == "reroll_dice":
            result = state.reaction_engine.apply_damage_reroll_action(
                state,
                action,
                decision,
            )
            return self._finish_decision_execution(state, decision, result)
        if decision.kind == "reaction":
            result = state.reaction_engine.apply_reaction_action(
                state,
                action,
                decision,
            )
            return self._finish_decision_execution(state, decision, result)
        return self._apply_selected_action(state, action, decision)

    def advance(self, state: EncounterState) -> EncounterProgress:
        """Resolve scripted actions until input, pacing, or a transition stops us.

        An already completed encounter returns its transition without selecting
        another action.

        >>> from unittest.mock import Mock
        >>> state = Mock(decision_stack=[])
        >>> state.turn_lifecycle.check_transition.return_value = "victory-scene"
        >>> EncounterOrchestrator().advance(state).transition
        'victory-scene'
        """
        progress = EncounterProgress()
        automatic_actions_resolved = 0
        while True:
            self._record_transition(state, progress)
            if progress.transition is not None:
                break
            if state.decision_stack:
                progress.paused_for_decision = True
                break

            creature_ref = state.turn_lifecycle.active_turn_creature(state)
            if not state.creatures[creature_ref].is_alive:
                state.turn_lifecycle.skip_defeated_turn(state, progress)
                state.turn_lifecycle.maybe_reset_reactions(state)
                continue
            if (
                state.automatic_action_limit is not None
                and automatic_actions_resolved >= state.automatic_action_limit
            ):
                progress.paused_for_pacing = True
                break
            selected_action = state._action_selectors[creature_ref].select_action(
                state,
                creature_ref,
                tuple(
                    state._available_creature_actions(
                        creature_ref,
                        include_attack_alternatives=True,
                    )
                ),
            )
            if selected_action is None:
                progress.paused_for_decision = True
                break

            remaining_limit = (
                None
                if state.automatic_action_limit is None
                else state.automatic_action_limit - automatic_actions_resolved
            )
            completed_turn, actor_progress, actions_resolved = self._run_creature_turn(
                state,
                creature_ref,
                initial_action=selected_action,
                action_limit=remaining_limit,
            )
            automatic_actions_resolved += actions_resolved
            state._merge_progress(progress, actor_progress)
            if progress.transition is not None or progress.paused_for_decision:
                break
            if completed_turn:
                self._finish_turn(state, creature_ref, progress)
                self._record_transition(state, progress)
                if progress.transition is not None:
                    break
        return progress

    def _continue_after_interrupt(
        self,
        state: EncounterState,
        progress: EncounterProgress,
    ) -> EncounterProgress:
        if (
            progress.transition is not None
            or progress.paused_for_decision
            or state.decision_stack
        ):
            return progress
        state._merge_progress(progress, self.advance(state))
        return progress

    def _finish_decision_execution(
        self,
        state: EncounterState,
        decision: DecisionFrame,
        result: DecisionExecutionResult,
    ) -> EncounterProgress:
        progress = result.progress
        if result.completed:
            self._continuation_runner.complete_decision(
                state,
                decision,
                action_id=result.action_id,
                progress=progress,
            )
        self._record_transition(state, progress)
        return self._continue_after_interrupt(state, progress)

    def _record_transition(
        self,
        state: EncounterState,
        progress: EncounterProgress,
    ) -> None:
        if progress.transition is None:
            progress.transition = state.turn_lifecycle.check_transition(state)

    def _finish_turn(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        progress: EncounterProgress,
    ) -> None:
        if state.creatures[creature_ref].is_alive:
            state.turn_lifecycle.advance_turn(state, progress)
        else:
            state.turn_lifecycle.skip_defeated_turn(state, progress)
        state.turn_lifecycle.maybe_reset_reactions(state)

    def _apply_selected_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        result = state._execute_creature_action(action, decision)
        progress = result.progress
        self._record_transition(state, progress)
        if progress.transition is not None:
            return progress
        if result.outcome is not ActionExecutionOutcome.END_TURN:
            return progress
        self._finish_turn(state, decision.creature_ref, progress)
        state._merge_progress(progress, self.advance(state))
        return progress

    def _run_creature_turn(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        *,
        initial_action: EncounterAction | None = None,
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        actor = state.creatures[creature_ref]
        progress = EncounterProgress()
        if not actor.is_alive:
            return True, progress, 0
        if actor.movement_remaining is None:
            actor.movement_remaining = state.turn_lifecycle.movement_budget_for_turn(
                state,
                creature_ref,
            )

        selector = state._action_selectors[creature_ref]
        action = initial_action or selector.select_action(
            state,
            creature_ref,
            tuple(
                state._available_creature_actions(
                    creature_ref,
                    include_attack_alternatives=True,
                )
            ),
        )
        if action is None:
            return False, progress, 0

        actions_resolved = 0
        while actor.is_alive:
            result = state._execute_creature_action(
                action,
                DecisionFrame(
                    id=f"turn-{creature_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    kind="turn",
                    reason="scripted_turn",
                ),
            )
            self._record_transition(state, result.progress)
            state._merge_progress(progress, result.progress)
            actions_resolved += 1
            if progress.transition is not None:
                return True, progress, actions_resolved
            if result.outcome is ActionExecutionOutcome.PAUSE_FOR_DECISION:
                return False, progress, actions_resolved
            if result.outcome is ActionExecutionOutcome.END_TURN or (
                action.kind == "attack" and actor.attacks_remaining == 0
            ):
                return True, progress, actions_resolved
            if action_limit is not None and actions_resolved >= action_limit:
                return False, progress, actions_resolved

            action = selector.select_action(
                state,
                creature_ref,
                tuple(
                    state._available_creature_actions(
                        creature_ref,
                        include_attack_alternatives=True,
                    )
                ),
            )
            if action is None:
                return False, progress, actions_resolved
        return True, progress, actions_resolved
