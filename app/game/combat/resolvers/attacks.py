from __future__ import annotations

from typing import TYPE_CHECKING

from ...models.actor import Actor
from ..attacks import apply_attack_damage, matching_damage_reroll_rule, resolve_attack, selected_attack_type
from ..models import EncounterAction, EncounterProgress
from ..refs import enemy_ref as _enemy_ref

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def resolve_player_attack_action(
    self: EncounterState,
    player: Actor,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    if not self.player_action_available and self.player_attacks_remaining <= 0:
        progress.messages.append(("system", "You have already used your Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "attack", "success": False},
            )
        )
        return
    if not isinstance(action.value, int):
        raise ValueError(
            f"Encounter attack action requires an integer target, got {action.value!r}."
        )
    enemy_index = action.value
    enemy = self.enemies[enemy_index]
    target_label = f"Enemy {enemy_index + 1} ({enemy.actor.name})"
    if self.player_action_available:
        self.player_action_available = False
        self.player_attacks_remaining = max(
            0,
            player.combat_profile.attacks_per_attack_action - 1,
        )
    elif self.player_attacks_remaining > 0:
        self.player_attacks_remaining -= 1

    nearby_opponents = tuple(
        other_enemy.position
        for other_enemy in self.enemies
        if other_enemy.is_alive
    )
    attack = resolve_attack(
        player,
        enemy.actor,
        attacker_label=player.name,
        target_label=target_label,
        items_by_id=self.item_templates,
        attacker_position=self.player_position,
        nearby_opponent_positions=nearby_opponents,
        attack_roll_mode_override=self._attack_roll_mode_for(
            "player",
            _enemy_ref(enemy_index),
            selected_attack_type(player, self.item_templates),
            self.player_position,
            nearby_opponents,
        ),
        d20_roller=_roll_die,
        dice_roller=_roll_dice,
    )
    reroll_rule = matching_damage_reroll_rule(player, attack)
    if attack.hit and reroll_rule is not None:
        self._open_damage_reroll_decision(
            attack=attack,
            rule=reroll_rule,
            target_index=enemy_index,
            attacker_label=player.name,
            target_label=target_label,
            action_id=action_id,
            progress=progress,
        )
        return
    apply_attack_damage(
        attack,
        enemy.actor,
        attacker_label=player.name,
        target_label=target_label,
    )
    progress.messages.extend(attack.messages)
    progress.events.append(
        self._event(
            "attack_resolved",
            actor_ref="player",
            action_id=action_id,
            data={
                "attacker_label": player.name,
                "target_ref": _enemy_ref(enemy_index),
                "target_label": target_label,
                "attacks_remaining": self.player_attacks_remaining,
                "attack_roll": attack.attack_roll,
                "attack_roll_detail": attack.attack_roll_detail,
                "hit": attack.hit,
                "critical_hit": attack.critical_hit,
                "damage": attack.damage,
                "damage_roll_detail": attack.damage_roll_detail,
            },
        )
    )
    if not enemy.is_alive:
        progress.events.append(
            self._event(
                "actor_defeated",
                actor_ref=_enemy_ref(enemy_index),
                action_id=action_id,
            )
        )
