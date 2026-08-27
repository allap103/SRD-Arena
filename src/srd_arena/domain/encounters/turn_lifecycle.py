from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.runtime import UntilTurnEnd, UntilTurnStart
from ..geometry import MovementBudget, MovementCost
from .attack_economy import clear_attack_action
from .models import (
    CreatureRef,
    EncounterProgress,
)
from .ongoing_effects import (
    expire_ongoing_effects_for_turn_start,
    resolve_end_turn_effects,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class TurnLifecycle:
    """Apply turn-boundary rules without deciding the encounter's control flow."""

    def movement_budget_for_turn(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> MovementBudget:
        return state.combat_rules.movement_budget(state, creature_ref).budget

    def active_turn_creature(self, state: EncounterState) -> CreatureRef:
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

    def advance_turn(
        self,
        state: EncounterState,
        progress: EncounterProgress | None = None,
    ) -> None:
        ending_creature_ref = state.current_decision().creature_ref
        ending_round = state.round.number
        resolve_end_turn_effects(state, ending_creature_ref, progress)
        self.expire_conditions_for_turn_end(state, ending_creature_ref, ending_round)
        self._advance_initiative(state)
        self._begin_turn_if_alive(state, progress)

    def skip_defeated_turn(
        self,
        state: EncounterState,
        progress: EncounterProgress | None = None,
    ) -> None:
        """Advance one defeated initiative slot without running its turn hooks."""
        self._advance_initiative(state)
        self._begin_turn_if_alive(state, progress)

    def _advance_initiative(self, state: EncounterState) -> None:
        state.turn_index += 1
        if state.turn_index >= self.turn_count(state):
            state.turn_index = 0
            state.round.advance()

    def _begin_turn_if_alive(
        self,
        state: EncounterState,
        progress: EncounterProgress | None,
    ) -> None:
        creature_ref = state.initiative_order[state.turn_index]
        creature_state = state.creatures[creature_ref]
        if not creature_state.is_alive:
            return
        for candidate in state.creatures.values():
            candidate.creature.reset_per_turn_modifiers()
        expire_ongoing_effects_for_turn_start(state, creature_ref)
        self.expire_conditions_for_turn_start(
            state,
            creature_ref,
            state.round.number,
        )
        from .actions.stat_block import recharge_stat_block_actions

        recharge_stat_block_actions(creature_state.creature)
        creature_state.movement_remaining = None
        creature_state.movement_spent_this_turn = MovementCost(0)
        creature_state.actions_remaining = 1
        creature_state.action_used_this_turn = False
        creature_state.magic_actions_remaining = 1
        clear_attack_action(creature_state)
        creature_state.bonus_action_available = True
        creature_state.bonus_action_used_this_turn = False
        if progress is not None:
            progress.messages.append(("turn", f"{creature_state.creature.name}'s turn"))

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

    def expire_conditions_for_turn_start(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        round_number: int,
    ) -> None:
        expired_ids = {
            condition.id
            for condition in state.conditions
            if isinstance(condition.duration, UntilTurnStart)
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

    def active_movement_remaining(self, state: EncounterState) -> MovementBudget:
        creature_ref = state.current_decision().creature_ref
        if state._is_grappled(creature_ref):
            return MovementBudget(0)
        if state.active_movement_remaining is None:
            state.active_movement_remaining = state.combat_rules.movement_budget(
                state,
                creature_ref,
            ).budget
        return state.active_movement_remaining

    def turn_count(self, state: EncounterState) -> int:
        return len(state.initiative_order)


TURN_LIFECYCLE = TurnLifecycle()
