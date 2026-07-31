from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.runtime import UntilTurnEnd
from .behaviors import movement_squares as _movement_squares
from .models import (
    ActionExecutionOutcome,
    CreatureRef,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class TurnEngine:
    def continue_after_interrupt(
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
        follow_up = self.advance_until_next_decision(state)
        state._merge_progress(progress, follow_up)
        return progress

    def apply_selected_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        result = state._execute_creature_action(action, decision)
        progress = result.progress
        if result.outcome is not ActionExecutionOutcome.END_TURN:
            return progress
        self.advance_turn(state)
        self.maybe_reset_reactions(state)
        follow_up = self.advance_until_next_decision(state)
        state._merge_progress(progress, follow_up)
        return progress

    def advance_until_next_decision(
        self,
        state: EncounterState,
    ) -> EncounterProgress:
        progress = EncounterProgress()
        automatic_actions_resolved = 0
        while True:
            transition = self.check_transition(state)
            if transition is not None:
                progress.transition = transition
                break
            if state.decision_stack:
                progress.paused_for_decision = True
                break
            creature_ref = self.active_turn_creature(state)
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
            completed_turn, enemy_progress, actions_resolved = self.run_creature_turn(
                state,
                creature_ref,
                initial_action=selected_action,
                action_limit=remaining_limit,
            )
            automatic_actions_resolved += actions_resolved
            state._merge_progress(progress, enemy_progress)
            if progress.transition is not None or progress.paused_for_decision:
                break
            if completed_turn:
                self.advance_turn(state)
                self.maybe_reset_reactions(state)
                progress.transition = self.check_transition(state)
                if progress.transition is not None:
                    break
            if (
                state.automatic_action_limit is not None
                and automatic_actions_resolved >= state.automatic_action_limit
            ):
                progress.paused_for_pacing = True
                break
        return progress

    def run_creature_turn(
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
            actor.movement_remaining = _movement_squares(actor.creature)

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
            state._merge_progress(progress, result.progress)
            actions_resolved += 1
            if result.outcome is ActionExecutionOutcome.ENCOUNTER_COMPLETE:
                return True, progress, actions_resolved
            if result.outcome is ActionExecutionOutcome.PAUSE_FOR_REACTION:
                return False, progress, actions_resolved
            if result.outcome is ActionExecutionOutcome.END_TURN or (
                action.kind == "attack"
                and actor.attacks_remaining == 0
                and not actor.pending_multiattack
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

    def active_turn_creature(self, state: EncounterState) -> CreatureRef:
        self.normalize_turn(state)
        return state.initiative_order[state.turn_index]

    def check_transition(self, state: EncounterState) -> str | None:
        configured_teams = {
            state._creature_team_id(creature_ref) for creature_ref in state.creatures
        }
        living_teams = {
            state._creature_team_id(creature_ref)
            for creature_ref, creature_state in state.creatures.items()
            if creature_state.is_alive
        }
        if len(configured_teams) > 1 and len(living_teams) <= 1:
            return (
                state.definition.victory.next_encounter_id
                if state.definition.victory
                else None
            )
        return None

    def advance_turn(self, state: EncounterState) -> None:
        ending_creature_ref = state.current_decision().creature_ref
        ending_round = state.round.number
        self.expire_conditions_for_turn_end(state, ending_creature_ref, ending_round)
        state.turn_index += 1
        if state.turn_index >= self.turn_count(state):
            state.turn_index = 0
            state.round.advance()
        self.normalize_turn(state)
        creature_ref = state.initiative_order[state.turn_index]
        creature_state = state.creatures[creature_ref]
        from .actions.stat_block import recharge_stat_block_actions

        recharge_stat_block_actions(creature_state.creature)
        creature_state.movement_remaining = None
        creature_state.actions_remaining = 1
        creature_state.magic_actions_remaining = 1
        creature_state.attacks_remaining = 0
        creature_state.pending_multiattack.clear()
        creature_state.bonus_action_available = True

    def expire_conditions_for_turn_end(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        round_number: int,
    ) -> None:
        expired_ids = {
            condition.id
            for condition in state.conditions
            if isinstance(condition.duration, UntilTurnEnd)
            and condition.duration.creature_ref == creature_ref
            and (
                condition.duration.round_number is None
                or state.round.matches(condition.duration.round_number)
            )
        }
        state.conditions = [
            condition
            for condition in state.conditions
            if condition.id not in expired_ids
        ]
        state.relationships = [
            relationship
            for relationship in state.relationships
            if relationship.identity.parent_id not in expired_ids
        ]

    def maybe_reset_reactions(self, state: EncounterState) -> None:
        if state.turn_index != 0:
            return
        for creature_state in state.creatures.values():
            creature_state.reaction_available = True

    def normalize_turn(self, state: EncounterState) -> None:
        if state.turn_index >= self.turn_count(state):
            state.turn_index = 0

        for _ in range(self.turn_count(state)):
            creature_ref = state.initiative_order[state.turn_index]
            if state.creatures[creature_ref].is_alive:
                return
            state.turn_index += 1
            if state.turn_index >= self.turn_count(state):
                state.turn_index = 0
                state.round.advance()

    def active_movement_remaining(self, state: EncounterState) -> int:
        creature_ref = state.current_decision().creature_ref
        if state._is_grappled(creature_ref):
            return 0
        if state.active_movement_remaining is None:
            actor = state.creatures[creature_ref].creature
            state.active_movement_remaining = _movement_squares(actor)
        return state.active_movement_remaining

    def turn_count(self, state: EncounterState) -> int:
        return len(state.initiative_order)

    def is_within_bounds(self, state: EncounterState, x: int, y: int) -> bool:
        return (
            0 <= x < state.definition.grid.width
            and 0 <= y < state.definition.grid.height
        )


TURN_ENGINE = TurnEngine()
