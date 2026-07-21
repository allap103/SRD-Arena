from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..scene import Position
from ..creatures import can_grapple
from ..rules.dice import resolve_d20
from ..effects.results import EffectResult
from .attacks import has_free_hand
from .behaviors import DIRECTION_DELTAS, is_adjacent as _is_adjacent
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


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def apply_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> EncounterProgress:
    decision = self.current_decision()
    if self._creature_controller(decision.actor_ref) != "user":
        raise RuntimeError("User action requested for an AI-controlled creature.")
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
    elif action.kind == "grapple":
        self._resolve_grapple_action(player, action, progress, resolved_action_id)
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
    player: Creature,
    direction: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    dx, dy = DIRECTION_DELTAS[direction]
    movement_cost = self._movement_cost_for(player, "player")
    if movement_cost is None:
        progress.messages.append(("system", "You cannot move while grappled."))
        return
    if self._player_movement_remaining(player) < movement_cost:
        progress.messages.append(("system", "You do not have enough movement remaining."))
        return

    moving_refs = {"player", *self._grappling_targets_for("player")}
    next_player_position = Position(self.player_position.x + dx, self.player_position.y + dy)
    next_target_positions = {
        target_ref: Position(target_position.x + dx, target_position.y + dy)
        for target_ref in self._grappling_targets_for("player")
        if (target_position := self._creature_position(target_ref)) is not None
    }
    if not self._position_is_free(
        next_player_position.x,
        next_player_position.y,
        ignored_refs=moving_refs,
    ) or any(
        not self._position_is_free(
            target_position.x,
            target_position.y,
            ignored_refs=moving_refs,
        )
        for target_position in next_target_positions.values()
    ):
        progress.messages.append(("system", "You cannot move there while grappling."))
        return

    self.player_position = next_player_position
    for target_ref, target_position in next_target_positions.items():
        if target_ref == "player":
            continue
        if target_ref.startswith("enemy:"):
            self.enemies[int(target_ref.split(":", 1)[1])].position = target_position
    self.player_movement_remaining = self._player_movement_remaining(player) - movement_cost
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


def resolve_grapple_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    if self.player_actions_remaining <= 0:
        progress.messages.append(("system", "You have already used your Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return
    if not isinstance(action.value, int):
        raise ValueError(
            f"Encounter grapple action requires an integer target, got {action.value!r}."
        )

    target_index = action.value
    target = self.enemies[target_index]
    if not target.is_alive:
        progress.messages.append(("system", "The target is no longer available."))
        return
    if not _is_adjacent(self.player_position, target.position):
        progress.messages.append(("system", "The target is out of reach."))
        return
    if not has_free_hand(player):
        progress.messages.append(("system", "You need a free hand to grapple."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return
    if not can_grapple(target.creature.size, player.size):
        progress.messages.append(("system", "The target is too large to grapple."))
        return

    self._consume_action(allow_magic=False)

    player_roll = resolve_d20(modifier=player.get_modifier(player.attributes.strength), roller=_roll_die)
    target_roll = resolve_d20(modifier=target.creature.get_modifier(target.creature.attributes.strength), roller=_roll_die)
    success = player_roll.total >= target_roll.total
    target_label = f"Enemy {target_index + 1} ({target.creature.name})"

    progress.events.append(
        self._event(
            "grapple_resolved",
            actor_ref="player",
            action_id=action_id,
            data={
                "target_ref": f"enemy:{target_index}",
                "target_label": target_label,
                "player_roll": player_roll.total,
                "target_roll": target_roll.total,
                "player_die": player_roll.selected,
                "target_die": target_roll.selected,
                "success": success,
            },
        )
    )

    if not success:
        progress.messages.append(("system", f"{player.name} fails to grapple {target_label}."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return

    progress.messages.append(("system", f"{player.name} grapples {target_label}."))
    progress.messages.append(("system", f"{target_label} is grappled."))
    self._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref=f"enemy:{target_index}",
                data={
                    "condition": "grappled",
                    "source_ref": "player",
                    "source_label": player.name,
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "grappling",
                    "source_ref": f"enemy:{target_index}",
                    "source_label": target.creature.name,
                },
            ),
        ]
    )
    progress.events.append(
        self._event(
            "action_resolved",
            actor_ref="player",
            action_id=action_id,
            data={"kind": "grapple", "success": True, "target_ref": f"enemy:{target_index}"},
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
