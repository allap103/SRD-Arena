from __future__ import annotations

from typing import TYPE_CHECKING

from ..geometry import Position
from .actions.attack_resolution import (
    attack_range_squares,
)
from .behaviors import (
    chebyshev_distance as _chebyshev_distance,
    movement_squares as _movement_squares,
)
from .models import (
    BehaviorContext,
    CreatureRef,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class TurnEngine:
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
            if state.decision_stack and state._creature_controller(
                state.current_decision().creature_ref
            ) == "external":
                progress.paused_for_decision = True
                break
            creature_ref = self.active_turn_creature(state)
            if state._creature_controller(creature_ref) == "external":
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
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        actor = state.creatures[creature_ref]
        progress = EncounterProgress()
        if not actor.is_alive:
            return True, progress, 0
        target_refs = [
            target_ref
            for target_ref in state._living_creature_refs()
            if state._creatures_are_opponents(creature_ref, target_ref)
        ]
        if not target_refs:
            return True, progress, 0
        target_ref = min(
            target_refs,
            key=lambda ref: (
                abs(state._creature_position(ref).x - actor.position.x)
                + abs(state._creature_position(ref).y - actor.position.y)
            ),
        )
        target_state = state.creatures[target_ref]
        if actor.movement_remaining is None:
            actor.movement_remaining = _movement_squares(actor.creature)

        behavior = state._behaviors[creature_ref]
        actions_resolved = 0
        while actor.is_alive and target_state.is_alive:
            command = behavior.send(
                BehaviorContext(
                    target_position=Position(
                        target_state.position.x,
                        target_state.position.y,
                    ),
                    actor_position=Position(actor.position.x, actor.position.y),
                    can_attack=(
                        _chebyshev_distance(
                            target_state.position,
                            actor.position,
                        )
                        <= attack_range_squares(
                            actor.creature,
                            state.item_templates,
                            preferred_attack_type=(
                                "ranged"
                                if actor.behavior.type == "archer"
                                else "melee"
                            ),
                        )
                        and state._creatures_are_opponents(
                            creature_ref,
                            target_ref,
                        )
                    ),
                )
            )
            if command is None:
                break
            action = self._select_behavior_action(
                state,
                command,
                creature_ref=creature_ref,
                target_ref=target_ref,
            )
            resolved = state._apply_creature_action(
                action,
                DecisionFrame(
                    id=f"turn-{creature_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    kind="turn",
                    reason="scripted_turn",
                ),
                continue_encounter=False,
            )
            state._merge_progress(progress, resolved)
            actions_resolved += 1
            if progress.transition is not None:
                return True, progress, actions_resolved
            if progress.paused_for_decision:
                return False, progress, actions_resolved
            if action.kind == "wait" or (
                action.kind == "attack"
                and actor.attacks_remaining == 0
                and not actor.pending_multiattack
            ):
                return True, progress, actions_resolved
            if action_limit is not None and actions_resolved >= action_limit:
                return False, progress, actions_resolved
        return True, progress, actions_resolved

    def _select_behavior_action(
        self,
        state: EncounterState,
        command: EncounterAction,
        *,
        creature_ref: CreatureRef,
        target_ref: CreatureRef,
    ) -> EncounterAction:
        available_actions = state._available_creature_actions(creature_ref)
        if command.kind == "attack":
            multiattack = next(
                (
                    action
                    for action in available_actions
                    if action.kind == "multiattack"
                ),
                None,
            )
            if multiattack is not None:
                return multiattack
        matching_action = next(
            (
                action
                for action in available_actions
                if action.kind == command.kind
                and (
                    action.value == command.value
                    or (
                        command.kind == "attack"
                        and action.value == target_ref
                    )
                )
            ),
            None,
        )
        preferred_attack_type = (
            str(command.value)
            if command.kind == "attack"
            and command.value in {"melee", "ranged"}
            else None
        )
        if matching_action is not None:
            matching_action.preferred_attack_type = preferred_attack_type
            return matching_action
        if command.kind != "attack":
            return next(
                action
                for action in available_actions
                if action.kind == "wait"
            )
        return EncounterAction(
            label=command.label,
            kind=command.kind,
            value=target_ref if command.kind == "attack" else command.value,
            id=f"{creature_ref}-scripted-{command.kind}",
            creature_ref=creature_ref,
            preferred_attack_type=preferred_attack_type,
            cost=command.cost,
        )

    def active_turn_creature(self, state: EncounterState) -> CreatureRef:
        self.normalize_turn(state)
        return state.initiative_order[state.turn_index]

    def check_transition(self, state: EncounterState) -> str | None:
        configured_teams = {
            state._creature_team_id(creature_ref)
            for creature_ref in state.creatures
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
        state.conditions = [
            condition
            for condition in state.conditions
            if not (
                condition.expires_on_creature_ref == creature_ref
                and state.round.matches(condition.expires_on_round)
            )
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
        return 0 <= x < state.definition.grid.width and 0 <= y < state.definition.grid.height


TURN_ENGINE = TurnEngine()
