from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.actor import Actor
from ..models.scene import Position
from .behaviors import DIRECTION_DELTAS
from .models import EncounterAction, EncounterProgress
from .resolvers import (
    apply_user_controlled_enemy_action as _apply_user_controlled_enemy_action_impl,
    resolve_feature_action as _resolve_feature_action_impl,
    resolve_flee_action as _resolve_flee_action_impl,
    resolve_player_attack_action as _resolve_player_attack_action_impl,
    resolve_spell_action as _resolve_spell_action_impl,
    resolve_utilize_action as _resolve_utilize_action_impl,
    resolve_wait_action as _resolve_wait_action_impl,
    user_controlled_enemy_actions as _user_controlled_enemy_actions_impl,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_action(
    self: EncounterState,
    player: Actor,
    action: EncounterAction,
) -> EncounterProgress:
    decision = self.current_decision()
    if self._actor_controller(decision.actor_ref) != "user":
        raise RuntimeError("User action requested for an AI-controlled actor.")
    if decision.actor_ref != "player":
        return self._apply_user_controlled_enemy_action(player, action, decision)
    if decision.kind == "reroll_dice":
        return self._apply_damage_reroll_action(player, action, decision)
    if decision.kind == "reaction":
        return self._apply_reaction_action(player, action, decision)

    progress = EncounterProgress()
    resolved_action_id = self._next_action_id()
    progress.events.append(
        self._event(
            "action_declared",
            actor_ref="player",
            action_id=resolved_action_id,
            data={
                "kind": action.kind,
                "value": action.value,
                "selected_action_id": action.id,
            },
        )
    )

    if action.kind == "move":
        direction = str(action.value)
        progress.messages.extend(
            self._resolve_enemy_opportunity_attacks_against_player(
                player,
                direction,
                resolved_action_id,
                progress,
            )
        )
        if player.get_health() > 0:
            self._apply_player_move(player, direction, progress, resolved_action_id)
    elif action.kind == "attack":
        self._resolve_player_attack_action(player, action, progress, resolved_action_id)
    elif action.kind == "utilize":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter utilize action requires an item id, got {action.value!r}."
            )
        self._resolve_utilize_action(player, action.value, progress, resolved_action_id)
    elif action.kind == "feature":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter feature action requires a feature id, got {action.value!r}."
            )
        self._resolve_feature_action(player, action.value, progress, resolved_action_id)
    elif action.kind == "spell":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter spell action requires a spell payload, got {action.value!r}."
            )
        self._resolve_spell_action(player, action.value, progress, resolved_action_id)
    elif action.kind == "wait":
        self._resolve_wait_action(progress, resolved_action_id)
    elif action.kind == "flee":
        self._resolve_flee_action(progress, resolved_action_id)
        return progress

    progress.transition = self._check_transition()
    if progress.transition is not None or player.get_health() <= 0:
        return progress
    if action.kind != "wait":
        return progress

    self._advance_turn()
    self._maybe_reset_reactions()
    follow_up = self.advance_until_next_decision(player)
    self._merge_progress(progress, follow_up)
    return progress


def apply_player_move(
    self: EncounterState,
    player: Actor,
    direction: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    dx, dy = DIRECTION_DELTAS[direction]
    self.player_position = Position(self.player_position.x + dx, self.player_position.y + dy)
    self.player_movement_remaining = self._player_movement_remaining(player) - 1
    progress.messages.append(
        (
            "system",
            f"You move {direction}. Movement remaining: {self.player_movement_remaining}.",
        )
    )
    progress.events.append(
        self._event(
            "movement_resolved",
            actor_ref="player",
            action_id=action_id,
            data={
                "direction": direction,
                "to": {"x": self.player_position.x, "y": self.player_position.y},
            },
        )
    )


resolve_player_attack_action = _resolve_player_attack_action_impl
resolve_wait_action = _resolve_wait_action_impl
resolve_flee_action = _resolve_flee_action_impl
user_controlled_enemy_actions = _user_controlled_enemy_actions_impl
apply_user_controlled_enemy_action = _apply_user_controlled_enemy_action_impl
resolve_utilize_action = _resolve_utilize_action_impl
resolve_feature_action = _resolve_feature_action_impl
resolve_spell_action = _resolve_spell_action_impl
