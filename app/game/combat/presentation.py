from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.actor import Actor
from ..models.status import Status
from .behaviors import movement_squares as _movement_squares
from .refs import enemy_ref as _enemy_ref

if TYPE_CHECKING:
    from .encounter import EncounterState


def render(self: EncounterState, player: Actor) -> str:
    player_movement_remaining = self._player_movement_remaining(player)
    rows = []
    for y in range(self.definition.grid.height):
        row = []
        for x in range(self.definition.grid.width):
            if self.player_position.x == x and self.player_position.y == y:
                row.append("P")
                continue
            live_enemy = self._live_enemy_at(x, y)
            row.append("E" if live_enemy else ".")
        rows.append(" ".join(row))

    enemy_lines = [
        (
            f"- Enemy {index + 1} ({enemy.actor.name}): "
            f"{enemy.actor.get_health()} HP at ({enemy.position.x}, {enemy.position.y})"
            f"{_condition_suffix(self.conditions_for(_enemy_ref(index)))}"
        )
        for index, enemy in enumerate(self.enemies)
        if enemy.is_alive
    ]
    if not enemy_lines:
        enemy_lines = ["- No enemies remaining."]

    return "\n".join(
        [
            *rows,
            "",
            f"Round {self.round_number} - Turn: {self.current_turn_label()}",
            f"Movement remaining: {player_movement_remaining}/{_movement_squares(player)} squares",
            (
                f"Player HP: {player.get_health()}/{player.get_max_health()} "
                f"at ({self.player_position.x}, {self.player_position.y})"
                f"{_condition_suffix(self.conditions_for('player'))}"
            ),
            f"Actions remaining: {self.player_actions_remaining}",
            f"Attacks remaining in action: {self.player_attacks_remaining}",
            f"Reaction available: {'yes' if self.player_reaction_available else 'no'}",
            "Enemies:",
            *enemy_lines,
        ]
    )


def export_decision(self: EncounterState) -> dict[str, object]:
    decision = self.current_decision()
    payload: dict[str, object] = {
        "frame_id": decision.id,
        "actor_ref": decision.actor_ref,
        "kind": decision.kind,
        "reason": decision.reason,
        "can_pass": decision.can_pass,
        "parent_frame_id": decision.parent_frame_id,
        "parent_action_id": decision.parent_action_id,
    }
    if self.pending_action is not None:
        payload["pending_action_id"] = self.pending_action.id
    return payload


def export_state(self: EncounterState, player: Actor) -> dict[str, object]:
    active_actor_ref = self.current_decision().actor_ref
    return {
        "scene_id": self.scene_id,
        "grid": {
            "width": self.definition.grid.width,
            "height": self.definition.grid.height,
        },
        "round_number": self.round_number,
        "turn_index": self.turn_index,
        "initiative_order": list(self.initiative_order),
        "initiative": [
            {
                "actor_ref": entry.actor_ref,
                "label": self._actor_label(entry.actor_ref),
                "roll": entry.roll,
                "modifier": entry.modifier,
                "total": entry.total,
            }
            for entry in self.initiative_entries
        ],
        "control_mode": self.control_mode,
        "active_actor_ref": active_actor_ref,
        "active_controller": self._actor_controller(active_actor_ref),
        "player": {
            "actor_id": player.id,
            "name": player.name,
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
            "team_id": self._actor_team_id("player"),
            "controller": self._actor_controller("player"),
        },
        "enemies": [
            {
                "actor_ref": _enemy_ref(index),
                "actor_id": enemy.actor_id,
                "name": enemy.actor.name,
                "position": {"x": enemy.position.x, "y": enemy.position.y},
                "health": enemy.actor.get_health(),
                "reaction_available": enemy.reaction_available,
                "conditions": [
                    condition.name
                    for condition in self.conditions_for(_enemy_ref(index))
                ],
                "movement_remaining": (
                    enemy.movement_remaining
                    if enemy.movement_remaining is not None
                    else _movement_squares(enemy.actor)
                ),
                "movement_total": _movement_squares(enemy.actor),
                "movement_remaining_feet": (
                    (
                        enemy.movement_remaining
                        if enemy.movement_remaining is not None
                        else _movement_squares(enemy.actor)
                    )
                    * enemy.actor.attributes.movement.feet_per_square
                ),
                "movement_total_feet": enemy.actor.attributes.movement.speed_feet,
                "max_health": enemy.actor.get_max_health(),
                "team_id": self._actor_team_id(_enemy_ref(index)),
                "controller": self._actor_controller(_enemy_ref(index)),
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
        "actor_ref": self.pending_action.actor_ref,
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
