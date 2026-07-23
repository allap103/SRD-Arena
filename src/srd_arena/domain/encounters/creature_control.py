from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature, can_grapple
from ..geometry import Position
from .actions.attack_resolution import (
    apply_attack_damage,
    has_free_hand,
    resolve_attack,
    selected_attack_type,
)
from .actions.consumables import healing_potions_in_inventory
from .behaviors import DIRECTION_DELTAS, is_adjacent as _is_adjacent, movement_squares as _movement_squares
from .models import ActionCost, CreatureRef, DecisionFrame, EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from .encounter import EncounterState


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def _lower_initial(label: str) -> str:
    return label[:1].lower() + label[1:]


def available_creature_actions(
    self: EncounterState,
    player: Creature,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    enemy = self.creatures[creature_ref]
    movement_cost = self._movement_cost_for(player, creature_ref)
    if enemy.movement_remaining is None:
        enemy.movement_remaining = _movement_squares(enemy.creature)
    actions: list[EncounterAction] = []
    if movement_cost is not None and enemy.movement_remaining >= movement_cost:
        moving_refs = {creature_ref, *self._grappling_targets_for(creature_ref)}
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
                    id=f"{creature_ref}-move-{direction}",
                    creature_ref=creature_ref,
                    cost=ActionCost(movement=movement_cost),
                )
            )
    can_attack = enemy.actions_remaining > 0 or enemy.attacks_remaining > 0
    if can_attack:
        for target_ref in self._living_creature_refs(player):
            if target_ref == creature_ref or not self._creatures_are_opponents(creature_ref, target_ref):
                continue
            if not _is_adjacent(enemy.position, self._creature_position(target_ref)):
                continue
            actions.append(
                EncounterAction(
                    f"Attack {_lower_initial(self._creature_label(target_ref))}",
                    "attack",
                    target_ref,
                    id=f"{creature_ref}-attack-{target_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    cost=ActionCost(
                        action=1 if enemy.attacks_remaining == 0 else 0
                    ),
                )
            )
            if (
                enemy.actions_remaining > 0
                and has_free_hand(enemy.creature)
                and can_grapple(
                    self.creatures[target_ref].creature.size,
                    enemy.creature.size,
                )
            ):
                actions.append(
                    EncounterAction(
                        f"Grapple {_lower_initial(self._creature_label(target_ref))}",
                        "grapple",
                        target_ref,
                        id=f"{creature_ref}-grapple-{target_ref.replace(':', '-')}",
                        creature_ref=creature_ref,
                        cost=ActionCost(action=1),
                    )
                )
    actions.extend(self._available_feature_actions(enemy.creature))
    actions.extend(self._available_spell_actions(enemy.creature))
    if enemy.bonus_action_available:
        for item in healing_potions_in_inventory(
            enemy.creature,
            self.item_templates,
        ):
            actions.append(
                EncounterAction(
                    f"Drink {item.name}",
                    "utilize",
                    item.id,
                    id=f"{creature_ref}-utilize-drink-{item.id}",
                    creature_ref=creature_ref,
                    cost=ActionCost(bonus_action=1),
                )
            )
    actions.append(
        EncounterAction(
            "Wait",
            "wait",
            id=f"{creature_ref}-wait",
            creature_ref=creature_ref,
        )
    )
    return actions


def apply_creature_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
    decision: DecisionFrame,
) -> EncounterProgress:
    enemy = self.creatures[decision.creature_ref]
    progress = EncounterProgress()
    action_id = self._next_action_id()
    progress.events.append(
        self._event(
            "action_declared",
            creature_ref=decision.creature_ref,
            action_id=action_id,
            data={
                "kind": action.kind,
                "value": action.value,
                "selected_action_id": action.id,
            },
        )
    )
    action_ends_turn = action.kind == "wait"

    if action.kind == "move":
        direction = str(action.value)
        dx, dy = DIRECTION_DELTAS[direction]
        destination = Position(enemy.position.x + dx, enemy.position.y + dy)
        movement_cost = self._movement_cost_for(
            enemy.creature,
            decision.creature_ref,
        )
        if movement_cost is None:
            raise RuntimeError("Movement is unavailable for this creature.")
        remaining = max(
            0,
            (enemy.movement_remaining or 0) - movement_cost,
        )
        grappled_refs = self._grappling_targets_for(decision.creature_ref)
        grappled_positions = {
            target_ref: Position(
                self.creatures[target_ref].position.x + dx,
                self.creatures[target_ref].position.y + dy,
            )
            for target_ref in grappled_refs
        }
        if self.reaction_engine.queue_opportunity_attack(
            self,
            mover_ref=decision.creature_ref,
            action_id=action_id,
            direction=direction,
            from_position=Position(enemy.position.x, enemy.position.y),
            to_position=destination,
            remaining_movement_after=remaining,
            progress=progress,
            user_controlled_only=True,
        ):
            progress.paused_for_decision = True
            return progress
        progress.messages.extend(
            self.reaction_engine.resolve_automatic_opportunity_attacks(
                self,
                mover_ref=decision.creature_ref,
                from_position=Position(enemy.position.x, enemy.position.y),
                to_position=destination,
                action_id=action_id,
                progress=progress,
            )
        )
        if not enemy.is_alive:
            return progress
        enemy.position = destination
        for target_ref, target_position in grappled_positions.items():
            self.creatures[target_ref].position = target_position
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
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={
                    "direction": direction,
                    "to": {"x": destination.x, "y": destination.y},
                },
            )
        )
    elif action.kind == "attack":
        if enemy.attacks_remaining == 0:
            if enemy.actions_remaining <= 0:
                raise RuntimeError("No Action remains to make an attack.")
            self._consume_action(allow_magic=False)
            enemy.attacks_remaining = max(
                0,
                enemy.creature.combat_profile.attacks_per_attack_action - 1,
            )
        else:
            enemy.attacks_remaining -= 1
        if not isinstance(action.value, str):
            raise ValueError("Attack action requires a creature reference.")
        target_ref = action.value
        if not self._creatures_are_opponents(decision.creature_ref, target_ref):
            raise ValueError("Attack target must belong to an opposing team.")
        defender = self._creature_for_ref(player, target_ref)
        target_label = self._creature_label(target_ref)
        attacker_label = enemy.creature.name
        nearby_opponent_positions = tuple(
            self.creatures[opponent_ref].position
            for opponent_ref in self._living_creature_refs(player)
            if self._creatures_are_opponents(
                decision.creature_ref,
                opponent_ref,
            )
        )
        attack = resolve_attack(
            enemy.creature,
            defender,
            attacker_label=attacker_label,
            target_label=target_label,
            items_by_id=self.item_templates,
            attacker_position=enemy.position,
            nearby_opponent_positions=nearby_opponent_positions,
            attack_roll_mode_override=self._attack_roll_mode_for(
                decision.creature_ref,
                target_ref,
                selected_attack_type(enemy.creature, self.item_templates),
                enemy.position,
                nearby_opponent_positions,
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
                creature_ref=decision.creature_ref,
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
                    "attacks_remaining": enemy.attacks_remaining,
                },
            )
        )
        if defender.get_health() <= 0:
            progress.events.append(
                self._event(
                    "creature_defeated",
                    creature_ref=target_ref,
                    action_id=action_id,
                )
            )
    elif action.kind == "feature":
        if not isinstance(action.value, str):
            raise ValueError("Feature action requires a feature id.")
        self._resolve_feature_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "grapple":
        self._resolve_grapple_action(
            enemy.creature,
            action,
            progress,
            action_id,
        )
    elif action.kind == "utilize":
        if not isinstance(action.value, str):
            raise ValueError("Utilize action requires an item id.")
        self._resolve_utilize_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "spell":
        if not isinstance(action.value, str):
            raise ValueError("Spell action requires a spell payload.")
        self._resolve_spell_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "wait":
        progress.messages.append(("system", f"{enemy.creature.name} waits."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "wait"},
            )
        )
    else:
        raise ValueError(f"Unsupported user-controlled enemy action: {action.kind}")

    progress.transition = self._check_transition()
    if progress.transition is not None or player.get_health() <= 0 or not action_ends_turn:
        return progress
    self._advance_turn()
    self._maybe_reset_reactions()
    follow_up = self.advance_until_next_decision(player)
    self._merge_progress(progress, follow_up)
    return progress
