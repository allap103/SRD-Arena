from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..geometry import Position
from .actions.attack_resolution import apply_attack_damage, resolve_attack, selected_attack_type
from .behaviors import DIRECTION_DELTAS, is_adjacent as _is_adjacent, movement_squares as _movement_squares
from .models import CreatureRef, BehaviorContext, EncounterEnemyState, EncounterProgress
from .refs import enemy_index as _enemy_index, enemy_ref as _enemy_ref

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
                state.current_decision().actor_ref
            ) == "user":
                progress.paused_for_decision = True
                break
            creature_type, enemy_index = self.active_turn_actor(state)
            actor_ref = (
                "player"
                if creature_type == "player"
                else _enemy_ref(enemy_index if enemy_index is not None else 0)
            )
            if state._creature_controller(actor_ref) == "user":
                progress.paused_for_decision = True
                break
            if creature_type == "player":
                break
            assert enemy_index is not None
            remaining_limit = (
                None
                if state.ai_action_limit is None
                else state.ai_action_limit - ai_actions_resolved
            )
            completed_turn, enemy_progress, actions_resolved = self.run_enemy_turn(
                state,
                player,
                enemy_index,
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

    def run_enemy_turn(
        self,
        state: EncounterState,
        player: Creature,
        enemy_index: int,
        *,
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        enemy = state.enemies[enemy_index]
        progress = EncounterProgress()
        if not enemy.is_alive:
            return True, progress, 0
        if enemy.movement_remaining is None:
            enemy.movement_remaining = _movement_squares(enemy.creature)

        behavior = state._behaviors[enemy_index]
        actions_resolved = 0
        while enemy.is_alive and player.get_health() > 0:
            command = behavior.send(
                BehaviorContext(
                    player_position=Position(
                        state.player_position.x,
                        state.player_position.y,
                    ),
                    enemy_position=Position(enemy.position.x, enemy.position.y),
                    can_attack=(
                        _is_adjacent(state.player_position, enemy.position)
                        and state._actors_are_opponents(
                            _enemy_ref(enemy_index),
                            "player",
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
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": command.kind, "value": command.value},
                )
            )

            if command.kind == "move":
                movement_cost = state._movement_cost_for(player, _enemy_ref(enemy_index))
                if movement_cost is None or enemy.movement_remaining < movement_cost:
                    break
                direction = str(command.value)
                dx, dy = DIRECTION_DELTAS[direction]
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                grappling_targets = state._grappling_targets_for(_enemy_ref(enemy_index))
                moving_refs = {_enemy_ref(enemy_index), *grappling_targets}
                target_positions = {
                    _enemy_ref(enemy_index): Position(target_x, target_y),
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
                if state.reaction_engine.queue_player_opportunity_attack(
                    state,
                    player,
                    enemy_index,
                    action_id,
                    direction,
                    Position(enemy.position.x, enemy.position.y),
                    Position(target_x, target_y),
                    enemy.movement_remaining - movement_cost,
                    progress,
                ):
                    progress.paused_for_decision = True
                    return False, progress, actions_resolved
                enemy.position = Position(target_x, target_y)
                for target_ref, target_position in target_positions.items():
                    if target_ref == _enemy_ref(enemy_index):
                        continue
                    if target_ref == "player":
                        state.player_position = target_position
                    else:
                        state.enemies[_enemy_index(target_ref)].position = target_position
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
                        actor_ref=_enemy_ref(enemy_index),
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
                attack = resolve_attack(
                    enemy.creature,
                    player,
                    attacker_label=f"Enemy {enemy_index + 1} ({enemy.creature.name})",
                    target_label=player.name,
                    items_by_id=state.item_templates,
                    attacker_position=enemy.position,
                    nearby_opponent_positions=(state.player_position,),
                    preferred_attack_type=preferred_attack_type,
                    attack_roll_mode_override=state._attack_roll_mode_for(
                        player,
                        _enemy_ref(enemy_index),
                        "player",
                        selected_attack_type(
                            enemy.creature,
                            state.item_templates,
                            preferred_attack_type=preferred_attack_type,
                        ),
                        enemy.position,
                        (state.player_position,),
                    ),
                    d20_roller=_roll_die,
                    dice_roller=_roll_dice,
                )
                apply_attack_damage(
                    attack,
                    player,
                    attacker_label=f"Enemy {enemy_index + 1} ({enemy.creature.name})",
                    target_label=player.name,
                )
                progress.messages.extend(attack.messages)
                progress.events.append(
                    state._event(
                        "attack_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "attacker_label": f"Enemy {enemy_index + 1} ({enemy.creature.name})",
                            "target_ref": "player",
                            "target_label": player.name,
                            "attack_roll": attack.attack_roll,
                            "attack_roll_detail": attack.attack_roll_detail,
                            "hit": attack.hit,
                            "critical_hit": attack.critical_hit,
                            "damage": attack.damage,
                            "damage_roll_detail": attack.damage_roll_detail,
                        },
                    )
                )
                actions_resolved += 1
                return True, progress, actions_resolved

            progress.messages.append(("system", f"{enemy.creature.name} waits."))
            progress.events.append(
                state._event(
                    "action_resolved",
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": "wait"},
                )
            )
            actions_resolved += 1
            return True, progress, actions_resolved
        return True, progress, actions_resolved

    def active_turn_actor(self, state: EncounterState) -> tuple[str, int | None]:
        self.normalize_turn(state)
        actor_ref = state.initiative_order[state.turn_index]
        if actor_ref == "player":
            return ("player", None)
        return ("enemy", _enemy_index(actor_ref))

    def check_transition(self, state: EncounterState) -> str | None:
        opponents = [
            enemy
            for index, enemy in enumerate(state.enemies)
            if state._actors_are_opponents("player", _enemy_ref(index))
        ]
        if opponents and all(not enemy.is_alive for enemy in opponents):
            return (
                state.definition.victory.next_encounter_id
                if state.definition.victory
                else None
            )
        return None

    def advance_turn(self, state: EncounterState) -> None:
        ending_creature_ref = state.current_decision().actor_ref
        ending_round = state.round.number
        self.expire_conditions_for_turn_end(state, ending_creature_ref, ending_round)
        state.turn_index += 1
        if state.turn_index >= self.turn_count(state):
            state.turn_index = 0
            state.round.advance()
        self.normalize_turn(state)
        actor_ref = state.initiative_order[state.turn_index]
        if actor_ref == "player":
            state.player_movement_remaining = None
            state.player_actions_remaining = 1
            state.player_magic_actions_remaining = 1
            state.player_attacks_remaining = 0
            state.player_bonus_action_available = True
        else:
            state.enemies[_enemy_index(actor_ref)].movement_remaining = None

    def expire_conditions_for_turn_end(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        round_number: int,
    ) -> None:
        state.conditions = [
            condition
            for condition in state.conditions
            if not (
                condition.expires_on_creature_ref == actor_ref
                and state.round.matches(condition.expires_on_round)
            )
        ]

    def maybe_reset_reactions(self, state: EncounterState) -> None:
        if state.turn_index != 0:
            return
        state.player_reaction_available = True
        for enemy in state.enemies:
            enemy.reaction_available = True

    def normalize_turn(self, state: EncounterState) -> None:
        if state.turn_index >= self.turn_count(state):
            state.turn_index = 0

        for _ in range(self.turn_count(state)):
            actor_ref = state.initiative_order[state.turn_index]
            if actor_ref == "player":
                return
            enemy = state.enemies[_enemy_index(actor_ref)]
            if enemy.is_alive:
                return
            state.turn_index += 1
            if state.turn_index >= self.turn_count(state):
                state.turn_index = 0
                state.round.advance()

    def player_movement_remaining(self, state: EncounterState, player: Creature) -> int:
        if state._is_grappled("player"):
            return 0
        if state.player_movement_remaining is None:
            state.player_movement_remaining = _movement_squares(player)
        return state.player_movement_remaining

    def turn_count(self, state: EncounterState) -> int:
        return len(state.initiative_order)

    def live_enemy_at(
        self,
        state: EncounterState,
        x: int,
        y: int,
    ) -> EncounterEnemyState | None:
        return next(
            (
                enemy
                for enemy in state.enemies
                if enemy.is_alive and enemy.position.x == x and enemy.position.y == y
            ),
            None,
        )

    def is_free_for_enemy(self, state: EncounterState, x: int, y: int) -> bool:
        if not self.is_within_bounds(state, x, y):
            return False
        if state.player_position.x == x and state.player_position.y == y:
            return False
        return self.live_enemy_at(state, x, y) is None

    def is_within_bounds(self, state: EncounterState, x: int, y: int) -> bool:
        return 0 <= x < state.definition.grid.width and 0 <= y < state.definition.grid.height


TURN_ENGINE = TurnEngine()
