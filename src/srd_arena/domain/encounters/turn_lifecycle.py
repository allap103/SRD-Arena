"""Start, end, and advance creature turns in initiative order."""

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
        """Return the grid movement budget available at turn start.

        >>> from unittest.mock import Mock
        >>> state = Mock()
        >>> state.combat_rules.movement_budget.return_value.budget = MovementBudget(6)
        >>> TurnLifecycle().movement_budget_for_turn(state, "hero")
        6
        """
        return state.combat_rules.movement_budget(state, creature_ref).budget

    def active_turn_creature(self, state: EncounterState) -> CreatureRef:
        """Return the creature occupying the current initiative slot.

        >>> from unittest.mock import Mock
        >>> TurnLifecycle().active_turn_creature(
        ...     Mock(initiative_order=["goblin", "hero"], turn_index=1))
        'hero'
        """
        return state.initiative_order[state.turn_index]

    def check_transition(self, state: EncounterState) -> str | None:
        """Return the victory transition once only one configured team lives.

        >>> from unittest.mock import Mock
        >>> state = Mock(creatures={"hero": Mock(is_alive=True), "goblin": Mock(is_alive=False)})
        >>> state._creature_team_id.side_effect = {"hero": "heroes", "goblin": "foes"}.__getitem__
        >>> state.definition.victory.next_encounter_id = "victory"
        >>> TurnLifecycle().check_transition(state)
        'victory'
        """
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
        """Run end hooks, advance initiative, and begin the next living turn.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.models import DecisionFrame
        >>> state = Mock(ongoing_effects=[], conditions=[], relationships=[], turn_index=0,
        ...     initiative_order=["hero", "fallen"],
        ...     creatures={"hero": Mock(is_alive=True), "fallen": Mock(is_alive=False)},
        ...     round=Mock(number=1))
        >>> state.current_decision.return_value = DecisionFrame("turn", "hero", "turn", "active")
        >>> TurnLifecycle().advance_turn(state)
        >>> state.turn_index
        1
        """
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
        """Advance one defeated initiative slot without running its turn hooks.

        >>> from unittest.mock import Mock
        >>> state = Mock(turn_index=0, initiative_order=["fallen", "next"],
        ...     creatures={"next": Mock(is_alive=False)}, round=Mock())
        >>> TurnLifecycle().skip_defeated_turn(state)
        >>> state.turn_index
        1
        """
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
        """Remove conditions whose duration ends with this creature's turn.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.effects.conditions import Condition, build_applied_condition
        >>> condition = build_applied_condition(condition=Condition.STUNNED,
        ...     source_ref="mage", source_label="Mage", target_ref="hero",
        ...     duration=UntilTurnEnd("hero"))
        >>> state = Mock(conditions=[condition], relationships=[], round=Mock())
        >>> TurnLifecycle().expire_conditions_for_turn_end(state, "hero", 1)
        >>> state.conditions
        []
        """
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
        """Remove conditions whose duration ends when this creature's turn starts.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.effects.conditions import Condition, build_applied_condition
        >>> condition = build_applied_condition(condition=Condition.FRIGHTENED,
        ...     source_ref="dragon", source_label="Dragon", target_ref="hero",
        ...     duration=UntilTurnStart("hero"))
        >>> state = Mock(conditions=[condition], relationships=[], round=Mock())
        >>> TurnLifecycle().expire_conditions_for_turn_start(state, "hero", 1)
        >>> state.conditions
        []
        """
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
        """Restore reactions when initiative wraps to the first slot.

        >>> from unittest.mock import Mock
        >>> hero = Mock(reaction_available=False)
        >>> state = Mock(turn_index=0, creatures={"hero": hero})
        >>> TurnLifecycle().maybe_reset_reactions(state)
        >>> hero.reaction_available
        True
        """
        if state.turn_index != 0:
            return
        for creature_state in state.creatures.values():
            creature_state.reaction_available = True

    def active_movement_remaining(self, state: EncounterState) -> MovementBudget:
        """Lazily initialize and return the active creature's movement budget.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.models import DecisionFrame
        >>> state = Mock(active_movement_remaining=None)
        >>> state.current_decision.return_value = DecisionFrame("turn", "hero", "turn", "active")
        >>> state._is_grappled.return_value = False
        >>> state.combat_rules.movement_budget.return_value.budget = MovementBudget(6)
        >>> TurnLifecycle().active_movement_remaining(state)
        6
        >>> state.active_movement_remaining
        6
        """
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
        """Return the number of initiative slots in the encounter.

        >>> from unittest.mock import Mock
        >>> TurnLifecycle().turn_count(Mock(initiative_order=["hero", "goblin"]))
        2
        """
        return len(state.initiative_order)


TURN_LIFECYCLE = TurnLifecycle()
