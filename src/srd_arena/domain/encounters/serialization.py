from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..effects.conditions import Status
from .behaviors import movement_squares as _movement_squares
from .refs import enemy_ref as _enemy_ref

if TYPE_CHECKING:
    from .encounter import EncounterState


def export_decision(self: EncounterState) -> dict[str, object]:
    decision = self.current_decision()
    payload: dict[str, object] = {
        "frame_id": decision.id,
        "creature_ref": decision.creature_ref,
        "kind": decision.kind,
        "reason": decision.reason,
        "can_pass": decision.can_pass,
        "parent_frame_id": decision.parent_frame_id,
        "parent_action_id": decision.parent_action_id,
    }
    if self.pending_action is not None:
        payload["pending_action_id"] = self.pending_action.id
    return payload


def export_state(self: EncounterState, player: Creature) -> dict[str, object]:
    active_creature_ref = self.current_decision().creature_ref
    return {
        "encounter_id": self.encounter_id,
        "grid": {
            "width": self.definition.grid.width,
            "height": self.definition.grid.height,
        },
        "round_number": self.round_number,
        "turn_index": self.turn_index,
        "initiative_order": list(self.initiative_order),
        "initiative": [
            {
                "creature_ref": entry.creature_ref,
                "label": self._creature_label(entry.creature_ref),
                "roll": entry.roll,
                "modifier": entry.modifier,
                "total": entry.total,
            }
            for entry in self.initiative_entries
        ],
        "control_mode": self.control_mode,
        "active_creature_ref": active_creature_ref,
        "active_controller": self._creature_controller(active_creature_ref),
        "player": {
            "creature_id": player.id,
            "name": player.name,
            "token_image": player.token_image,
            "position": {"x": self.player_position.x, "y": self.player_position.y},
            "health": player.get_health(),
            "max_health": player.get_max_health(),
            "movement_remaining": self._player_movement_remaining(player),
            "movement_total": _movement_squares(player),
            "movement_remaining_feet": (
                self._player_movement_remaining(player)
                * player.attributes.movement.feet_per_square
            ),
            "movement_total_feet": player.attributes.movement.speed_feet,
            "action_available": self.player_action_available,
            "actions_remaining": self.player_actions_remaining,
            "attacks_remaining": self.player_attacks_remaining,
            "bonus_action_available": self.player_bonus_action_available,
            "reaction_available": self.player_reaction_available,
            "conditions": [
                condition.name for condition in self.conditions_for("player")
            ],
            "spell_slots_max": (
                {
                    str(level): slots
                    for level, slots in player.spellcasting.spell_slots_max.items()
                }
                if player.spellcasting is not None
                else {}
            ),
            "spell_slots_remaining": (
                {
                    str(level): slots
                    for level, slots in player.spellcasting.spell_slots_remaining.items()
                }
                if player.spellcasting is not None
                else {}
            ),
            "team_id": self._creature_team_id("player"),
            "controller": self._creature_controller("player"),
        },
        "enemies": [
            {
                "creature_ref": _enemy_ref(index),
                "creature_id": enemy.creature_id,
                "name": enemy.creature.name,
                "token_image": enemy.creature.token_image,
                "position": {"x": enemy.position.x, "y": enemy.position.y},
                "health": enemy.creature.get_health(),
                "reaction_available": enemy.reaction_available,
                "conditions": [
                    condition.name
                    for condition in self.conditions_for(_enemy_ref(index))
                ],
                "movement_remaining": (
                    enemy.movement_remaining
                    if enemy.movement_remaining is not None
                    else _movement_squares(enemy.creature)
                ),
                "movement_total": _movement_squares(enemy.creature),
                "movement_remaining_feet": (
                    (
                        enemy.movement_remaining
                        if enemy.movement_remaining is not None
                        else _movement_squares(enemy.creature)
                    )
                    * enemy.creature.attributes.movement.feet_per_square
                ),
                "movement_total_feet": enemy.creature.attributes.movement.speed_feet,
                "max_health": enemy.creature.get_max_health(),
                "team_id": self._creature_team_id(_enemy_ref(index)),
                "controller": self._creature_controller(_enemy_ref(index)),
                "is_alive": enemy.is_alive,
            }
            for index, enemy in enumerate(self.enemies)
        ],
        "decision": self.export_decision(),
        "pending_action": self._export_pending_action(),
    }


def export_pending_action(self: EncounterState) -> dict[str, object] | None:
    if self.pending_action is None:
        return None
    return {
        "id": self.pending_action.id,
        "kind": self.pending_action.kind,
        "creature_ref": self.pending_action.creature_ref,
        "direction": self.pending_action.direction,
        "from": {
            "x": self.pending_action.from_position.x,
            "y": self.pending_action.from_position.y,
        },
        "to": {
            "x": self.pending_action.to_position.x,
            "y": self.pending_action.to_position.y,
        },
        "resume_enemy_index": self.pending_action.resume_enemy_index,
        "remaining_movement_after": self.pending_action.remaining_movement_after,
        "trigger_id": self.pending_action.trigger_id,
    }


def _condition_suffix(conditions: tuple[Status, ...]) -> str:
    if not conditions:
        return ""
    labels = ", ".join(condition.name.capitalize() for condition in conditions)
    return f" [{labels}]"
