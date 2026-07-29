from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..geometry import Position
from ..actions.attack_resolution import (
    apply_attack_damage,
    resolve_attack,
    selected_attack_type,
)
from .behaviors import (
    DIRECTION_DELTAS,
    is_adjacent as _is_adjacent,
    movement_squares as _movement_squares,
)
from .models import (
    ActionCost,
    CreatureRef,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
)
from .refs import enemy_index as _enemy_index

if TYPE_CHECKING:
    from .encounter import EncounterState


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def user_controlled_enemy_actions(
    self: EncounterState,
    player: Creature,
    actor_ref: CreatureRef,
) -> list[EncounterAction]:
    enemy_index = _enemy_index(actor_ref)
    enemy = self.enemies[enemy_index]
    movement_cost = self.rules.movement_cost(player, actor_ref)
    if enemy.movement_remaining is None:
        enemy.movement_remaining = _movement_squares(enemy.creature)
    actions: list[EncounterAction] = []
    if movement_cost is not None and enemy.movement_remaining >= movement_cost:
        moving_refs = {actor_ref, *self.rules.grappling_targets(actor_ref)}
        for direction, (dx, dy) in DIRECTION_DELTAS.items():
            target_x = enemy.position.x + dx
            target_y = enemy.position.y + dy
            if not self._position_is_free(target_x, target_y, ignored_refs=moving_refs):
                continue
            actions.append(
                EncounterAction(
                    f"Move {direction}",
                    "move",
                    direction,
                    id=f"{actor_ref}-move-{direction}",
                    actor_ref=actor_ref,
                    cost=ActionCost(movement=1),
                )
            )
    for target_ref in self._living_creature_refs(player):
        if target_ref == actor_ref or not self.rules.are_opponents(
            actor_ref, target_ref
        ):
            continue
        if not _is_adjacent(enemy.position, self._creature_position(target_ref)):
            continue
        actions.append(
            EncounterAction(
                f"Attack {self._creature_label(target_ref)}",
                "attack",
                target_ref,
                id=f"{actor_ref}-attack-{target_ref.replace(':', '-')}",
                actor_ref=actor_ref,
                cost=ActionCost(action=1),
            )
        )
    actions.append(
        EncounterAction(
            "Wait",
            "wait",
            id=f"{actor_ref}-wait",
            actor_ref=actor_ref,
        )
    )
    return actions


def apply_user_controlled_enemy_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
    decision: DecisionFrame,
) -> EncounterProgress:
    enemy_index = _enemy_index(decision.actor_ref)
    enemy = self.enemies[enemy_index]
    progress = EncounterProgress()
    action_id = self._next_action_id()
    progress.events.append(
        self._event(
            "action_declared",
            actor_ref=decision.actor_ref,
            action_id=action_id,
            data={
                "kind": action.kind,
                "value": action.value,
                "selected_action_id": action.id,
            },
        )
    )
    action_ends_turn = action.kind in {"attack", "wait"}

    if action.kind == "move":
        direction = str(action.value)
        dx, dy = DIRECTION_DELTAS[direction]
        destination = Position(enemy.position.x + dx, enemy.position.y + dy)
        remaining = max(0, (enemy.movement_remaining or 0) - 1)
        if self._queue_player_opportunity_attack(
            player,
            enemy_index,
            action_id,
            direction,
            Position(enemy.position.x, enemy.position.y),
            destination,
            remaining,
            progress,
        ):
            progress.paused_for_decision = True
            return progress
        enemy.position = destination
        enemy.movement_remaining = remaining
        progress.messages.append(
            (
                "system",
                f"{enemy.creature.name} moves {direction} to "
                f"({destination.x}, {destination.y}).",
            )
        )
        progress.events.append(
            self._event(
                "movement_resolved",
                actor_ref=decision.actor_ref,
                action_id=action_id,
                data={
                    "direction": direction,
                    "to": {"x": destination.x, "y": destination.y},
                },
            )
        )
    elif action.kind == "attack":
        if not isinstance(action.value, str):
            raise ValueError("Attack action requires an creature reference.")
        target_ref = action.value
        if not self.rules.are_opponents(decision.actor_ref, target_ref):
            raise ValueError("Attack target must belong to an opposing team.")
        defender = self.rules.creature(player, target_ref)
        target_label = self._creature_label(target_ref)
        attacker_label = self._creature_label(decision.actor_ref)
        attack = resolve_attack(
            enemy.creature,
            defender,
            attacker_label=attacker_label,
            target_label=target_label,
            items_by_id=self.item_templates,
            attacker_position=enemy.position,
            nearby_opponent_positions=(self.player_position,),
            attack_roll_mode_override=self._attack_roll_mode_for(
                decision.actor_ref,
                target_ref,
                selected_attack_type(enemy.creature, self.item_templates),
                enemy.position,
                (self.player_position,),
            ),
            d20_roller=_roll_die,
            dice_roller=_roll_dice,
        )
        apply_attack_damage(
            attack,
            defender,
            attacker_label=attacker_label,
            target_label=target_label,
        )
        progress.messages.extend(attack.messages)
        progress.events.append(
            self._event(
                "attack_resolved",
                actor_ref=decision.actor_ref,
                action_id=action_id,
                data={
                    "attacker_label": attacker_label,
                    "target_ref": target_ref,
                    "target_label": target_label,
                    "attack_roll": attack.attack_roll,
                    "attack_roll_detail": attack.attack_roll_detail,
                    "hit": attack.hit,
                    "critical_hit": attack.critical_hit,
                    "damage": attack.damage,
                    "damage_roll_detail": attack.damage_roll_detail,
                },
            )
        )
        if defender.get_health() <= 0:
            progress.events.append(
                self._event(
                    "actor_defeated",
                    actor_ref=target_ref,
                    action_id=action_id,
                )
            )
    elif action.kind == "wait":
        progress.messages.append(("system", f"{enemy.creature.name} waits."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref=decision.actor_ref,
                action_id=action_id,
                data={"kind": "wait"},
            )
        )
    else:
        raise ValueError(f"Unsupported user-controlled enemy action: {action.kind}")

    progress.transition = self._check_transition()
    if (
        progress.transition is not None
        or player.get_health() <= 0
        or not action_ends_turn
    ):
        return progress
    self._advance_turn()
    self._maybe_reset_reactions()
    follow_up = self.advance_until_next_decision(player)
    self._merge_progress(progress, follow_up)
    return progress
