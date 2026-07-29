from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..geometry import Position
from ..creatures import can_grapple
from ..rolls.dice import resolve_d20
from ..effects.results import EffectResult
from .attacks import resolve_player_attack_action as _resolve_player_attack_action_impl
from .features import resolve_feature_action as _resolve_feature_action_impl
from .items import resolve_utilize_action as _resolve_utilize_action_impl
from .spells.casting import resolve_spell_action as _resolve_spell_action_impl
from .utility import resolve_wait_action as _resolve_wait_action_impl
from .attack_resolution import has_free_hand
from .pipeline import ACTION_PIPELINE, ActionExecutionContext
from ..encounters.behaviors import DIRECTION_DELTAS, is_adjacent as _is_adjacent
from ..encounters.models import EncounterAction, EncounterProgress
from ..encounters.enemy_control import (
    apply_user_controlled_enemy_action as _apply_user_controlled_enemy_action_impl,
    user_controlled_enemy_actions as _user_controlled_enemy_actions_impl,
)

if TYPE_CHECKING:
    from ..encounters.encounter import EncounterState


def _roll_die(sides: int) -> int:
    from ..encounters import encounter as encounter_module

    return encounter_module.roll_die(sides)


def apply_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> EncounterProgress:
    decision = self.current_decision()
    manages_own_lifecycle = (
        decision.actor_ref != "player"
        or decision.kind in {"reroll_dice", "reaction"}
    )

    def resolve(context: ActionExecutionContext) -> None:
        if decision.actor_ref != "player":
            resolved = self.actions.perform_for_controlled_enemy(
                player, context.action, decision
            )
        elif decision.kind == "reroll_dice":
            resolved = self._apply_damage_reroll_action(
                player, context.action, decision
            )
        elif decision.kind == "reaction":
            resolved = self._apply_reaction_action(
                player, context.action, decision
            )
        else:
            _resolve_normal_action(context)
            return
        self._merge_progress(context.progress, resolved)

    return ACTION_PIPELINE.execute(
        self,
        player,
        action,
        resolve,
        declare=not manages_own_lifecycle,
        check_transition=not manages_own_lifecycle,
        complete=not manages_own_lifecycle,
    )


def _resolve_normal_action(context: ActionExecutionContext) -> None:
    state = context.state
    player = context.player
    action = context.action
    progress = context.progress
    assert context.action_id is not None
    resolved_action_id = context.action_id
    if action.kind == "move":
        direction = str(action.value)
        progress.messages.extend(
            state._resolve_enemy_opportunity_attacks_against_player(
                player,
                direction,
                resolved_action_id,
                progress,
            )
        )
        if player.get_health() > 0:
            state.actions.move_player(player, direction, progress, resolved_action_id)
    elif action.kind == "attack":
        state.actions.resolve_attack(player, action, progress, resolved_action_id)
    elif action.kind == "grapple":
        state.actions.resolve_grapple(player, action, progress, resolved_action_id)
    elif action.kind == "utilize":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter utilize action requires an item id, got {action.value!r}."
            )
        state.actions.resolve_item(player, action.value, progress, resolved_action_id)
    elif action.kind == "feature":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter feature action requires a feature id, got {action.value!r}."
            )
        state.actions.resolve_feature(player, action.value, progress, resolved_action_id)
    elif action.kind == "spell":
        if not isinstance(action.value, str):
            raise ValueError(
                f"Encounter spell action requires a spell payload, got {action.value!r}."
            )
        state.actions.resolve_spell(player, action.value, progress, resolved_action_id)
    elif action.kind == "wait":
        state.actions.resolve_wait(progress, resolved_action_id)
    else:
        raise ValueError(f"Unsupported normal action kind: {action.kind}")


def apply_player_move(
    self: EncounterState,
    player: Creature,
    direction: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    dx, dy = DIRECTION_DELTAS[direction]
    movement_cost = self.rules.movement_cost(player, "player")
    if movement_cost is None:
        progress.messages.append(("system", "You cannot move while grappled."))
        return
    if self._player_movement_remaining(player) < movement_cost:
        progress.messages.append(
            ("system", "You do not have enough movement remaining.")
        )
        return

    moving_refs = {"player", *self.rules.grappling_targets("player")}
    next_player_position = Position(
        self.player_position.x + dx, self.player_position.y + dy
    )
    next_target_positions = {
        target_ref: Position(target_position.x + dx, target_position.y + dy)
        for target_ref in self.rules.grappling_targets("player")
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
    self.player_movement_remaining = (
        self._player_movement_remaining(player) - movement_cost
    )
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

    player_roll = resolve_d20(
        modifier=player.get_modifier(player.attributes.strength), roller=_roll_die
    )
    target_roll = resolve_d20(
        modifier=target.creature.get_modifier(target.creature.attributes.strength),
        roller=_roll_die,
    )
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
        progress.messages.append(
            ("system", f"{player.name} fails to grapple {target_label}.")
        )
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
            data={
                "kind": "grapple",
                "success": True,
                "target_ref": f"enemy:{target_index}",
            },
        )
    )


resolve_player_attack_action = _resolve_player_attack_action_impl
resolve_wait_action = _resolve_wait_action_impl
user_controlled_enemy_actions = _user_controlled_enemy_actions_impl
apply_user_controlled_enemy_action = _apply_user_controlled_enemy_action_impl
resolve_utilize_action = _resolve_utilize_action_impl
resolve_feature_action = _resolve_feature_action_impl
resolve_spell_action = _resolve_spell_action_impl
