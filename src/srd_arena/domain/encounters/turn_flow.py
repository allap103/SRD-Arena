from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..geometry import Position
from .actions.attack_resolution import (
    apply_attack_damage,
    attack_range_squares,
    resolve_attack,
    selected_attack_type,
)
from .actions.hit_effects import apply_attack_hit_effects
from .behaviors import (
    DIRECTION_DELTAS,
    chebyshev_distance as _chebyshev_distance,
    movement_squares as _movement_squares,
)
from .models import (
    BehaviorContext,
    CreatureRef,
    EncounterCreatureState,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


class TurnEngine:
    def advance_until_next_decision(
        self,
        state: EncounterState,
        player: Creature,
    ) -> EncounterProgress:
        progress = EncounterProgress()
        ai_actions_resolved = 0
        while True:
            if player.get_health() <= 0:
                break
            if state.decision_stack and state._creature_controller(
                state.current_decision().creature_ref
            ) == "user":
                progress.paused_for_decision = True
                break
            creature_ref = self.active_turn_creature(state)
            if state._creature_controller(creature_ref) == "user":
                progress.paused_for_decision = True
                break
            remaining_limit = (
                None
                if state.ai_action_limit is None
                else state.ai_action_limit - ai_actions_resolved
            )
            completed_turn, enemy_progress, actions_resolved = self.run_creature_turn(
                state,
                player,
                creature_ref,
                action_limit=remaining_limit,
            )
            ai_actions_resolved += actions_resolved
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
                state.ai_action_limit is not None
                and ai_actions_resolved >= state.ai_action_limit
            ):
                progress.paused_for_ai = True
                break
        return progress

    def run_creature_turn(
        self,
        state: EncounterState,
        player: Creature,
        creature_ref: CreatureRef,
        *,
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        enemy = state.creatures[creature_ref]
        progress = EncounterProgress()
        if not enemy.is_alive:
            return True, progress, 0
        target_refs = [
            target_ref
            for target_ref in state._living_creature_refs(player)
            if state._creatures_are_opponents(creature_ref, target_ref)
        ]
        if not target_refs:
            return True, progress, 0
        target_ref = min(
            target_refs,
            key=lambda ref: (
                abs(state._creature_position(ref).x - enemy.position.x)
                + abs(state._creature_position(ref).y - enemy.position.y)
            ),
        )
        target_state = state.creatures[target_ref]
        target = target_state.creature
        if enemy.movement_remaining is None:
            enemy.movement_remaining = _movement_squares(enemy.creature)

        behavior = state._behaviors[creature_ref]
        actions_resolved = 0
        while enemy.is_alive and target_state.is_alive:
            command = behavior.send(
                BehaviorContext(
                    target_position=Position(
                        target_state.position.x,
                        target_state.position.y,
                    ),
                    actor_position=Position(enemy.position.x, enemy.position.y),
                    can_attack=(
                        _chebyshev_distance(
                            target_state.position,
                            enemy.position,
                        )
                        <= attack_range_squares(
                            enemy.creature,
                            state.item_templates,
                            preferred_attack_type=(
                                "ranged"
                                if enemy.behavior.type == "archer"
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

            action_id = state._next_action_id()
            progress.events.append(
                state._event(
                    "action_declared",
                    creature_ref=creature_ref,
                    action_id=action_id,
                    data={"kind": command.kind, "value": command.value},
                )
            )

            if command.kind == "move":
                movement_cost = state._movement_cost_for(player, creature_ref)
                if movement_cost is None or enemy.movement_remaining < movement_cost:
                    break
                direction = str(command.value)
                dx, dy = DIRECTION_DELTAS[direction]
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                grappling_targets = state._grappling_targets_for(creature_ref)
                moving_refs = {creature_ref, *grappling_targets}
                target_positions = {
                    creature_ref: Position(target_x, target_y),
                    **{
                        target_ref: Position(
                            state._creature_position(target_ref).x + dx,
                            state._creature_position(target_ref).y + dy,
                        )
                        for target_ref in grappling_targets
                    },
                }
                if not state._position_is_free(target_x, target_y, ignored_refs=moving_refs) or any(
                    not state._position_is_free(
                        target_position.x,
                        target_position.y,
                        ignored_refs=moving_refs,
                    )
                    for target_position in target_positions.values()
                ):
                    break
                if state.reaction_engine.queue_opportunity_attack(
                    state,
                    mover_ref=creature_ref,
                    action_id=action_id,
                    direction=direction,
                    from_position=Position(enemy.position.x, enemy.position.y),
                    to_position=Position(target_x, target_y),
                    remaining_movement_after=enemy.movement_remaining - movement_cost,
                    progress=progress,
                    user_controlled_only=True,
                    excluded_reactor_refs=grappling_targets,
                ):
                    progress.paused_for_decision = True
                    return False, progress, actions_resolved
                progress.messages.extend(
                    state.reaction_engine.resolve_automatic_opportunity_attacks(
                        state,
                        mover_ref=creature_ref,
                        from_position=Position(
                            enemy.position.x,
                            enemy.position.y,
                        ),
                        to_position=Position(target_x, target_y),
                        action_id=action_id,
                        progress=progress,
                        excluded_reactor_refs=grappling_targets,
                    )
                )
                if not enemy.is_alive:
                    return True, progress, actions_resolved
                enemy.position = Position(target_x, target_y)
                for target_ref, target_position in target_positions.items():
                    if target_ref == creature_ref:
                        continue
                    state.creatures[target_ref].position = target_position
                enemy.movement_remaining -= movement_cost
                actions_resolved += 1
                progress.messages.append(
                    (
                        "system",
                        f"{enemy.creature.name} moves {direction} to ({target_x}, {target_y}).",
                    )
                )
                progress.events.append(
                    state._event(
                        "movement_resolved",
                        creature_ref=creature_ref,
                        action_id=action_id,
                        data={
                            "direction": direction,
                            "to": {"x": target_x, "y": target_y},
                        },
                    )
                )
                if action_limit is not None and actions_resolved >= action_limit:
                    return False, progress, actions_resolved
                continue

            if command.kind == "attack":
                preferred_attack_type = (
                    str(command.value)
                    if isinstance(command.value, str)
                    and command.value in {"melee", "ranged"}
                    else None
                )
                multiattack_sequence = (
                    enemy.creature.multiattack.executable_attack_sequence(
                        {
                            attack.name
                            for attack in enemy.creature.monster_attacks
                        }
                    )
                    if enemy.creature.multiattack is not None
                    else None
                )
                attack_names: tuple[str | None, ...] = (
                    tuple(multiattack_sequence)
                    if multiattack_sequence is not None
                    else (None,)
                )
                for attack_name in attack_names:
                    attack = resolve_attack(
                        enemy.creature,
                        target,
                        attacker_label=enemy.creature.name,
                        target_label=state._creature_label(target_ref),
                        items_by_id=state.item_templates,
                        attacker_position=enemy.position,
                        nearby_opponent_positions=(target_state.position,),
                        preferred_attack_type=preferred_attack_type,
                        preferred_attack_name=attack_name,
                        attack_roll_mode_override=state._attack_roll_mode_for(
                            creature_ref,
                            target_ref,
                            selected_attack_type(
                                enemy.creature,
                                state.item_templates,
                                preferred_attack_type=preferred_attack_type,
                            ),
                            enemy.position,
                            (target_state.position,),
                        ),
                        d20_roller=_roll_die,
                        dice_roller=_roll_dice,
                    )
                    apply_attack_damage(
                        attack,
                        target,
                        attacker_label=enemy.creature.name,
                        target_label=state._creature_label(target_ref),
                    )
                    if attack.hit and target.get_health() > 0:
                        apply_attack_hit_effects(
                            state,
                            attacker_ref=creature_ref,
                            target_ref=target_ref,
                            effects=attack.hit_effects,
                            progress=progress,
                        )
                    progress.messages.extend(attack.messages)
                    progress.events.append(
                        state._event(
                            "attack_resolved",
                            creature_ref=creature_ref,
                            action_id=action_id,
                            data={
                                "attacker_label": enemy.creature.name,
                                "target_ref": target_ref,
                                "target_label": state._creature_label(target_ref),
                                "attack_name": attack_name,
                                "attack_roll": attack.attack_roll,
                                "attack_roll_detail": attack.attack_roll_detail,
                                "hit": attack.hit,
                                "critical_hit": attack.critical_hit,
                                "damage": attack.damage,
                                "damage_roll_detail": attack.damage_roll_detail,
                            },
                        )
                    )
                    if not target_state.is_alive:
                        state._remove_relational_statuses_for_creature(
                            target_ref
                        )
                        break
                actions_resolved += len(attack_names)
                return True, progress, actions_resolved

            progress.messages.append(("system", f"{enemy.creature.name} waits."))
            progress.events.append(
                state._event(
                    "action_resolved",
                    creature_ref=creature_ref,
                    action_id=action_id,
                    data={"kind": "wait"},
                )
            )
            actions_resolved += 1
            return True, progress, actions_resolved
        return True, progress, actions_resolved

    def active_turn_creature(self, state: EncounterState) -> CreatureRef:
        self.normalize_turn(state)
        return state.initiative_order[state.turn_index]

    def check_transition(self, state: EncounterState) -> str | None:
        opponents = [
            creature_state
            for creature_ref, creature_state in state.creatures.items()
            if state._creatures_are_opponents(
                state.primary_creature_ref,
                creature_ref,
            )
        ]
        if opponents and all(not enemy.is_alive for enemy in opponents):
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
        creature_state.pending_attack_names.clear()
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

    def active_movement_remaining(self, state: EncounterState, player: Creature) -> int:
        creature_ref = state.current_decision().creature_ref
        if state._is_grappled(creature_ref):
            return 0
        if state.active_movement_remaining is None:
            state.active_movement_remaining = _movement_squares(player)
        return state.active_movement_remaining

    def turn_count(self, state: EncounterState) -> int:
        return len(state.initiative_order)

    def living_non_primary_creature_at(
        self,
        state: EncounterState,
        x: int,
        y: int,
    ) -> EncounterCreatureState | None:
        return next(
            (
                creature_state
                for creature_ref, creature_state in state.creatures.items()
                if creature_ref != state.primary_creature_ref
                and creature_state.is_alive
                and creature_state.position.x == x
                and creature_state.position.y == y
            ),
            None,
        )

    def is_within_bounds(self, state: EncounterState, x: int, y: int) -> bool:
        return 0 <= x < state.definition.grid.width and 0 <= y < state.definition.grid.height


TURN_ENGINE = TurnEngine()
