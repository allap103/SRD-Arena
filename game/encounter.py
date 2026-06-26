from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Generator

from .feature_actions import resolve_feature_action
from .models.actor import Actor
from .models.item import Item
from .models.scene import Behavior, Encounter, Position
from .systems.roll import roll_dice, roll_die

ActorRef = str

DIRECTION_DELTAS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up-left": (-1, -1),
    "up-right": (1, -1),
    "down-left": (-1, 1),
    "down-right": (1, 1),
}


@dataclass
class ActionCost:
    movement: int = 0
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0


@dataclass
class EncounterAction:
    label: str
    kind: str
    value: str | int | None = None
    id: str = ""
    actor_ref: ActorRef = "player"
    source_trigger_id: str | None = None
    cost: ActionCost = field(default_factory=ActionCost)


@dataclass
class DecisionFrame:
    id: str
    actor_ref: ActorRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


@dataclass
class CombatEvent:
    seq: int
    type: str
    actor_ref: ActorRef | None = None
    frame_id: str | None = None
    action_id: str | None = None
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class EncounterProgress:
    messages: list[tuple[str, str]] = field(default_factory=list)
    transition: str | None = None
    events: list[CombatEvent] = field(default_factory=list)
    paused_for_decision: bool = False


@dataclass
class BehaviorContext:
    player_position: Position
    enemy_position: Position
    can_attack: bool


@dataclass
class PendingAction:
    id: str
    kind: str
    actor_ref: ActorRef
    direction: str
    from_position: Position
    to_position: Position
    resume_enemy_index: int | None = None
    remaining_movement_after: int | None = None
    trigger_id: str | None = None


@dataclass
class EncounterEnemyState:
    actor_id: str
    actor: Actor
    position: Position
    behavior: Behavior
    patrol_index: int = 0
    reaction_available: bool = True

    @property
    def is_alive(self) -> bool:
        return self.actor.get_health() > 0


@dataclass
class EncounterSnapshotEnemy:
    actor_id: str
    current_health: int
    position: Position
    patrol_index: int = 0
    reaction_available: bool = True


@dataclass
class DecisionFrameSnapshot:
    id: str
    actor_ref: ActorRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


@dataclass
class PendingActionSnapshot:
    id: str
    kind: str
    actor_ref: ActorRef
    direction: str
    from_position: Position
    to_position: Position
    resume_enemy_index: int | None = None
    remaining_movement_after: int | None = None
    trigger_id: str | None = None


@dataclass
class EncounterSnapshot:
    scene_id: str
    player_position: Position
    turn_index: int = 0
    round_number: int = 1
    player_movement_remaining: int | None = None
    player_action_available: bool = True
    player_attacks_remaining: int = 0
    player_bonus_action_available: bool = True
    player_reaction_available: bool = True
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    decision_stack: list[DecisionFrameSnapshot] = field(default_factory=list)
    pending_action: PendingActionSnapshot | None = None
    enemies: list[EncounterSnapshotEnemy] = field(default_factory=list)


@dataclass
class AttackOutcome:
    messages: list[tuple[str, str]]
    hit: bool
    attack_roll: int
    damage: int
    defender_defeated: bool
    attack_roll_detail: dict[str, int]
    damage_roll_detail: dict[str, object] | None = None


@dataclass
class EncounterState:
    scene_id: str
    definition: Encounter
    player_position: Position
    enemies: list[EncounterEnemyState]
    turn_index: int = 0
    round_number: int = 1
    player_movement_remaining: int | None = None
    player_action_available: bool = True
    player_attacks_remaining: int = 0
    player_bonus_action_available: bool = True
    player_reaction_available: bool = True
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    decision_stack: list[DecisionFrame] = field(default_factory=list)
    pending_action: PendingAction | None = None
    item_templates: dict[str, Item] = field(default_factory=dict)
    _behaviors: list[Generator[EncounterAction | None, BehaviorContext, None]] = field(
        default_factory=list,
        repr=False,
    )

    @classmethod
    def from_definition(
        cls,
        scene_id: str,
        definition: Encounter,
        actor_templates: dict[str, Actor],
        item_templates: dict[str, Item] | None = None,
    ) -> EncounterState:
        enemies = [
            EncounterEnemyState(
                actor_id=enemy.actor_id,
                actor=deepcopy(actor_templates[enemy.actor_id]),
                position=Position(enemy.start.x, enemy.start.y),
                behavior=deepcopy(enemy.behavior),
            )
            for enemy in definition.enemies
        ]
        state = cls(
            scene_id=scene_id,
            definition=definition,
            player_position=Position(
                definition.player_start.x,
                definition.player_start.y,
            ),
            enemies=enemies,
            item_templates=item_templates or {},
        )
        state._initialize_behaviors()
        return state

    @classmethod
    def from_snapshot(
        cls,
        definition: Encounter,
        snapshot: EncounterSnapshot,
        actor_templates: dict[str, Actor],
        item_templates: dict[str, Item] | None = None,
    ) -> EncounterState:
        behavior_by_index = {index: enemy.behavior for index, enemy in enumerate(definition.enemies)}
        enemies = []
        for index, saved_enemy in enumerate(snapshot.enemies):
            actor = deepcopy(actor_templates[saved_enemy.actor_id])
            actor.current_health = saved_enemy.current_health
            enemies.append(
                EncounterEnemyState(
                    actor_id=saved_enemy.actor_id,
                    actor=actor,
                    position=Position(saved_enemy.position.x, saved_enemy.position.y),
                    behavior=deepcopy(behavior_by_index[index]),
                    patrol_index=saved_enemy.patrol_index,
                    reaction_available=saved_enemy.reaction_available,
                )
            )
        state = cls(
            scene_id=snapshot.scene_id,
            definition=definition,
            player_position=Position(snapshot.player_position.x, snapshot.player_position.y),
            enemies=enemies,
            turn_index=snapshot.turn_index,
            round_number=snapshot.round_number,
            player_movement_remaining=snapshot.player_movement_remaining,
            player_action_available=snapshot.player_action_available,
            player_attacks_remaining=snapshot.player_attacks_remaining,
            player_bonus_action_available=snapshot.player_bonus_action_available,
            player_reaction_available=snapshot.player_reaction_available,
            action_sequence=snapshot.action_sequence,
            frame_sequence=snapshot.frame_sequence,
            event_sequence=snapshot.event_sequence,
            decision_stack=[
                DecisionFrame(
                    id=frame.id,
                    actor_ref=frame.actor_ref,
                    kind=frame.kind,
                    reason=frame.reason,
                    parent_frame_id=frame.parent_frame_id,
                    parent_action_id=frame.parent_action_id,
                    can_pass=frame.can_pass,
                )
                for frame in snapshot.decision_stack
            ],
            pending_action=(
                PendingAction(
                    id=snapshot.pending_action.id,
                    kind=snapshot.pending_action.kind,
                    actor_ref=snapshot.pending_action.actor_ref,
                    direction=snapshot.pending_action.direction,
                    from_position=Position(
                        snapshot.pending_action.from_position.x,
                        snapshot.pending_action.from_position.y,
                    ),
                    to_position=Position(
                        snapshot.pending_action.to_position.x,
                        snapshot.pending_action.to_position.y,
                    ),
                    resume_enemy_index=snapshot.pending_action.resume_enemy_index,
                    remaining_movement_after=snapshot.pending_action.remaining_movement_after,
                    trigger_id=snapshot.pending_action.trigger_id,
                )
                if snapshot.pending_action is not None
                else None
            ),
            item_templates=item_templates or {},
        )
        state._initialize_behaviors()
        state._normalize_turn()
        return state

    def snapshot(self) -> EncounterSnapshot:
        return EncounterSnapshot(
            scene_id=self.scene_id,
            player_position=Position(self.player_position.x, self.player_position.y),
            turn_index=self.turn_index,
            round_number=self.round_number,
            player_movement_remaining=self.player_movement_remaining,
            player_action_available=self.player_action_available,
            player_attacks_remaining=self.player_attacks_remaining,
            player_bonus_action_available=self.player_bonus_action_available,
            player_reaction_available=self.player_reaction_available,
            action_sequence=self.action_sequence,
            frame_sequence=self.frame_sequence,
            event_sequence=self.event_sequence,
            decision_stack=[
                DecisionFrameSnapshot(
                    id=frame.id,
                    actor_ref=frame.actor_ref,
                    kind=frame.kind,
                    reason=frame.reason,
                    parent_frame_id=frame.parent_frame_id,
                    parent_action_id=frame.parent_action_id,
                    can_pass=frame.can_pass,
                )
                for frame in self.decision_stack
            ],
            pending_action=(
                PendingActionSnapshot(
                    id=self.pending_action.id,
                    kind=self.pending_action.kind,
                    actor_ref=self.pending_action.actor_ref,
                    direction=self.pending_action.direction,
                    from_position=Position(
                        self.pending_action.from_position.x,
                        self.pending_action.from_position.y,
                    ),
                    to_position=Position(
                        self.pending_action.to_position.x,
                        self.pending_action.to_position.y,
                    ),
                    resume_enemy_index=self.pending_action.resume_enemy_index,
                    remaining_movement_after=self.pending_action.remaining_movement_after,
                    trigger_id=self.pending_action.trigger_id,
                )
                if self.pending_action is not None
                else None
            ),
            enemies=[
                EncounterSnapshotEnemy(
                    actor_id=enemy.actor_id,
                    current_health=enemy.actor.get_health(),
                    position=Position(enemy.position.x, enemy.position.y),
                    patrol_index=enemy.patrol_index,
                    reaction_available=enemy.reaction_available,
                )
                for enemy in self.enemies
            ],
        )

    def _initialize_behaviors(self) -> None:
        self._behaviors = []
        for enemy in self.enemies:
            behavior = _build_behavior(enemy)
            next(behavior)
            self._behaviors.append(behavior)

    def render(self, player: Actor) -> str:
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
                ),
                f"Action available: {'yes' if self.player_action_available else 'no'}",
                f"Attacks remaining in action: {self.player_attacks_remaining}",
                f"Reaction available: {'yes' if self.player_reaction_available else 'no'}",
                "Enemies:",
                *enemy_lines,
            ]
        )

    def current_turn_label(self) -> str:
        decision = self.current_decision()
        if decision.kind == "reaction":
            return f"{self._actor_label(decision.actor_ref)} (Reaction)"
        return self._actor_label(decision.actor_ref)

    def current_decision(self) -> DecisionFrame:
        if self.decision_stack:
            return self.decision_stack[-1]
        actor_type, enemy_index = self._active_turn_actor()
        if actor_type == "player":
            return DecisionFrame(
                id="turn-player",
                actor_ref="player",
                kind="turn",
                reason="normal_turn",
            )
        assert enemy_index is not None
        return DecisionFrame(
            id=f"turn-enemy-{enemy_index}",
            actor_ref=_enemy_ref(enemy_index),
            kind="turn",
            reason="normal_turn",
        )

    def export_decision(self) -> dict[str, object]:
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

    def export_state(self, player: Actor) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "grid": {
                "width": self.definition.grid.width,
                "height": self.definition.grid.height,
            },
            "round_number": self.round_number,
            "turn_index": self.turn_index,
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
                "attacks_remaining": self.player_attacks_remaining,
                "bonus_action_available": self.player_bonus_action_available,
                "reaction_available": self.player_reaction_available,
            },
            "enemies": [
                {
                    "actor_ref": _enemy_ref(index),
                    "actor_id": enemy.actor_id,
                    "name": enemy.actor.name,
                    "position": {"x": enemy.position.x, "y": enemy.position.y},
                    "health": enemy.actor.get_health(),
                    "reaction_available": enemy.reaction_available,
                    "is_alive": enemy.is_alive,
                }
                for index, enemy in enumerate(self.enemies)
            ],
            "decision": self.export_decision(),
            "pending_action": self._export_pending_action(),
        }

    def active_actor(self) -> tuple[str, int | None]:
        actor_ref = self.current_decision().actor_ref
        if actor_ref == "player":
            return ("player", None)
        return ("enemy", _enemy_index(actor_ref))

    def available_actions(self, player: Actor) -> list[EncounterAction]:
        decision = self.current_decision()
        if decision.actor_ref != "player":
            return []
        if decision.kind == "reaction":
            return self._reaction_actions()

        actions = []
        if self._player_movement_remaining(player) > 0:
            for direction, (dx, dy) in DIRECTION_DELTAS.items():
                target_x = self.player_position.x + dx
                target_y = self.player_position.y + dy
                if not self._is_within_bounds(target_x, target_y):
                    continue
                if self._live_enemy_at(target_x, target_y) is not None:
                    continue
                actions.append(
                    EncounterAction(
                        f"Move {direction}",
                        "move",
                        direction,
                        id=f"player-move-{direction}",
                        actor_ref="player",
                        cost=ActionCost(movement=1),
                    )
                )

        can_attack = self.player_action_available or self.player_attacks_remaining > 0
        for index, enemy in enumerate(self.enemies):
            if can_attack and enemy.is_alive and _is_adjacent(self.player_position, enemy.position):
                actions.append(
                    EncounterAction(
                        f"Attack enemy {index + 1} ({enemy.actor.name})",
                        "attack",
                        index,
                        id=f"player-attack-{index}",
                        actor_ref="player",
                        cost=ActionCost(action=1 if self.player_action_available else 0),
                    )
                )

        actions.extend(self._available_feature_actions(player))

        if self.player_bonus_action_available:
            for item in _healing_potions_in_inventory(player, self.item_templates):
                actions.append(
                    EncounterAction(
                        f"Drink {item.name}",
                        "utilize",
                        item.id,
                        id=f"player-utilize-drink-{item.id}",
                        actor_ref="player",
                        cost=ActionCost(bonus_action=1),
                    )
                )

        actions.append(
            EncounterAction(
                "Wait",
                "wait",
                id="player-wait",
                actor_ref="player",
            )
        )

        if self.definition.flee and self.definition.flee.allowed:
            actions.append(
                EncounterAction(
                    "Flee encounter",
                    "flee",
                    id="player-flee",
                    actor_ref="player",
                )
            )

        return actions

    def _available_feature_actions(self, player: Actor) -> list[EncounterAction]:
        actions: list[EncounterAction] = []
        for feature_id, definition in player.combat_profile.feature_actions.items():
            if not self._feature_action_available(player, definition):
                continue
            action_cost = ActionCost(
                bonus_action=1 if definition.economy == "bonus_action" else 0,
                action=1 if definition.economy == "action" else 0,
                reaction=1 if definition.economy == "reaction" else 0,
            )
            actions.append(
                EncounterAction(
                    definition.label,
                    "feature",
                    feature_id,
                    id=f"player-feature-{feature_id.replace('_', '-')}",
                    actor_ref="player",
                    cost=action_cost,
                )
            )
        return actions

    def _feature_action_available(self, player: Actor, definition) -> bool:
        if definition.economy == "bonus_action" and not self.player_bonus_action_available:
            return False
        if definition.economy == "action" and not self.player_action_available:
            return False
        if definition.economy == "reaction" and not self.player_reaction_available:
            return False
        return player.feature_uses_remaining.get(definition.feature_id, 0) > 0

    def apply_action(
        self,
        player: Actor,
        action: EncounterAction,
    ) -> EncounterProgress:
        decision = self.current_decision()
        if decision.actor_ref != "player":
            raise RuntimeError("Player action requested while it is not the player's turn.")
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
        action_ends_turn = False

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
            if not self.player_action_available and self.player_attacks_remaining <= 0:
                progress.messages.append(("system", "You have already used your Action."))
                progress.events.append(
                    self._event(
                        "action_resolved",
                        actor_ref="player",
                        action_id=resolved_action_id,
                        data={"kind": "attack", "success": False},
                    )
                )
                return progress
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

            attack = _resolve_attack(
                player,
                enemy.actor,
                attacker_label=player.name,
                target_label=target_label,
                items_by_id=self.item_templates,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={
                        "attacker_label": player.name,
                        "target_ref": _enemy_ref(enemy_index),
                        "target_label": target_label,
                        "attacks_remaining": self.player_attacks_remaining,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
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
                        action_id=resolved_action_id,
                    )
                )
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
        elif action.kind == "wait":
            action_ends_turn = True
            progress.messages.append(("system", "You hold your ground."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={"kind": "wait"},
                )
            )
        elif action.kind == "flee":
            progress.messages.append(("system", "You flee the encounter."))
            progress.transition = self.definition.flee.next_scene if self.definition.flee else None
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={"kind": "flee"},
                )
            )
            return progress

        progress.transition = self._check_transition()
        if progress.transition is not None or player.get_health() <= 0:
            return progress

        if not action_ends_turn:
            return progress

        self._advance_turn()
        self._maybe_reset_reactions()
        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)
        return progress

    def advance_until_next_decision(self, player: Actor) -> EncounterProgress:
        progress = EncounterProgress()
        while True:
            if player.get_health() <= 0:
                break
            if self.decision_stack and self.current_decision().actor_ref == "player":
                progress.paused_for_decision = True
                break
            actor_type, enemy_index = self._active_turn_actor()
            if actor_type == "player":
                break
            assert enemy_index is not None
            completed_turn, enemy_progress = self._run_enemy_turn(
                player,
                enemy_index,
                _movement_squares(self.enemies[enemy_index].actor),
            )
            self._merge_progress(progress, enemy_progress)
            if progress.transition is not None or progress.paused_for_decision:
                break
            if completed_turn:
                self._advance_turn()
                self._maybe_reset_reactions()
                progress.transition = self._check_transition()
                if progress.transition is not None:
                    break
        return progress

    def _run_enemy_turn(
        self,
        player: Actor,
        enemy_index: int,
        movement_remaining: int,
    ) -> tuple[bool, EncounterProgress]:
        enemy = self.enemies[enemy_index]
        progress = EncounterProgress()
        if not enemy.is_alive:
            return True, progress

        behavior = self._behaviors[enemy_index]
        while enemy.is_alive and player.get_health() > 0:
            command = behavior.send(
                BehaviorContext(
                    player_position=Position(self.player_position.x, self.player_position.y),
                    enemy_position=Position(enemy.position.x, enemy.position.y),
                    can_attack=_is_adjacent(self.player_position, enemy.position),
                )
            )
            if command is None:
                break

            action_id = self._next_action_id()
            progress.events.append(
                self._event(
                    "action_declared",
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": command.kind, "value": command.value},
                )
            )

            if command.kind == "move":
                if movement_remaining <= 0:
                    break
                direction = str(command.value)
                dx, dy = DIRECTION_DELTAS[direction]
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                if not self._is_free_for_enemy(target_x, target_y):
                    break
                if self._queue_player_opportunity_attack(
                    enemy_index,
                    action_id,
                    direction,
                    Position(enemy.position.x, enemy.position.y),
                    Position(target_x, target_y),
                    movement_remaining - 1,
                    progress,
                ):
                    progress.paused_for_decision = True
                    return False, progress
                enemy.position = Position(target_x, target_y)
                movement_remaining -= 1
                progress.messages.append(
                    (
                        "system",
                        f"{enemy.actor.name} moves {direction} to ({target_x}, {target_y}).",
                    )
                )
                progress.events.append(
                    self._event(
                        "movement_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "direction": direction,
                            "to": {"x": target_x, "y": target_y},
                        },
                    )
                )
                continue

            if command.kind == "attack":
                attack = _resolve_attack(
                    enemy.actor,
                    player,
                    attacker_label=f"Enemy {enemy_index + 1} ({enemy.actor.name})",
                    target_label=player.name,
                    items_by_id=self.item_templates,
                )
                progress.messages.extend(attack.messages)
                progress.events.append(
                    self._event(
                        "attack_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "attacker_label": f"Enemy {enemy_index + 1} ({enemy.actor.name})",
                            "target_ref": "player",
                            "target_label": player.name,
                            "attack_roll": attack.attack_roll,
                            "attack_roll_detail": attack.attack_roll_detail,
                            "hit": attack.hit,
                            "damage": attack.damage,
                            "damage_roll_detail": attack.damage_roll_detail,
                        },
                    )
                )
                break

            progress.messages.append(("system", f"{enemy.actor.name} waits."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": "wait"},
                )
            )
            break
        return True, progress

    def _apply_reaction_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        progress = EncounterProgress()
        pending_action = self.pending_action
        if pending_action is None:
            raise RuntimeError("Reaction action requested without a pending action.")
        resolved_action_id = self._next_action_id()

        progress.events.append(
            self._event(
                "action_declared",
                actor_ref="player",
                frame_id=decision.id,
                action_id=resolved_action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "opportunity_attack":
            self.player_reaction_available = False
            target_index = _enemy_index(pending_action.actor_ref)
            target = self.enemies[target_index]
            target_label = f"Enemy {target_index + 1} ({target.actor.name})"
            attack = _resolve_attack(
                player,
                target.actor,
                attacker_label=player.name,
                target_label=target_label,
                action_label="Opportunity attack",
                items_by_id=self.item_templates,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    frame_id=decision.id,
                    action_id=resolved_action_id,
                    data={
                        "attacker_label": player.name,
                        "target_ref": pending_action.actor_ref,
                        "target_label": target_label,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if not target.is_alive:
                progress.events.append(
                    self._event(
                        "actor_defeated",
                        actor_ref=pending_action.actor_ref,
                        frame_id=decision.id,
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind != "pass":
            raise ValueError(f"Unsupported reaction action: {action.kind}")

        self.decision_stack.pop()
        progress.events.append(
            self._event(
                "decision_closed",
                actor_ref="player",
                frame_id=decision.id,
                action_id=resolved_action_id,
            )
        )

        self._resume_pending_action(player, progress)
        progress.transition = self._check_transition()
        if progress.transition is not None or player.get_health() <= 0:
            return progress

        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)
        return progress

    def _resume_pending_action(self, player: Actor, progress: EncounterProgress) -> None:
        pending_action = self.pending_action
        if pending_action is None:
            return
        self.pending_action = None
        if pending_action.kind != "move":
            return

        if pending_action.actor_ref == "player":
            return

        enemy_index = _enemy_index(pending_action.actor_ref)
        enemy = self.enemies[enemy_index]
        if enemy.is_alive and self._is_free_for_enemy(
            pending_action.to_position.x,
            pending_action.to_position.y,
        ):
            enemy.position = Position(
                pending_action.to_position.x,
                pending_action.to_position.y,
            )
            progress.messages.append(
                (
                    "system",
                    f"{enemy.actor.name} moves {pending_action.direction} to "
                    f"({pending_action.to_position.x}, {pending_action.to_position.y}).",
                )
            )
            progress.events.append(
                self._event(
                    "movement_resolved",
                    actor_ref=pending_action.actor_ref,
                    action_id=pending_action.id,
                    data={
                        "direction": pending_action.direction,
                        "to": {
                            "x": pending_action.to_position.x,
                            "y": pending_action.to_position.y,
                        },
                        "resumed": True,
                    },
                )
            )

        if pending_action.resume_enemy_index is None:
            return
        completed_turn, resumed = self._run_enemy_turn(
            player,
            pending_action.resume_enemy_index,
            pending_action.remaining_movement_after or 0,
        )
        self._merge_progress(progress, resumed)
        if completed_turn and not progress.paused_for_decision:
            self._advance_turn()
            self._maybe_reset_reactions()

    def _resolve_enemy_opportunity_attacks_against_player(
        self,
        player: Actor,
        direction: str,
        action_id: str,
        progress: EncounterProgress,
    ) -> list[tuple[str, str]]:
        dx, dy = DIRECTION_DELTAS[direction]
        origin = Position(self.player_position.x, self.player_position.y)
        destination = Position(self.player_position.x + dx, self.player_position.y + dy)
        messages: list[tuple[str, str]] = []
        threatened_by = [
            (index, enemy)
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
            and enemy.reaction_available
            and _is_adjacent(origin, enemy.position)
            and not _is_adjacent(destination, enemy.position)
        ]
        for index, enemy in threatened_by:
            enemy.reaction_available = False
            trigger_id = self._next_frame_id(prefix="trigger")
            progress.events.append(
                self._event(
                    "trigger_opened",
                    actor_ref=_enemy_ref(index),
                    action_id=action_id,
                    data={"kind": "opportunity_attack", "trigger_id": trigger_id},
                )
            )
            attack = _resolve_attack(
                enemy.actor,
                player,
                attacker_label=f"Enemy {index + 1} ({enemy.actor.name})",
                target_label=player.name,
                action_label="Opportunity attack",
                items_by_id=self.item_templates,
            )
            messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref=_enemy_ref(index),
                    action_id=action_id,
                    data={
                        "attacker_label": f"Enemy {index + 1} ({enemy.actor.name})",
                        "target_ref": "player",
                        "target_label": player.name,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if player.get_health() <= 0:
                break
        return messages

    def _resolve_utilize_action(
        self,
        player: Actor,
        item_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        item = self.item_templates.get(item_id)
        if item is None or not player.inventory.has_item(item_id):
            progress.messages.append(("system", "You do not have that item."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "utilize", "item_id": item_id, "success": False},
                )
            )
            return

        if not self.player_bonus_action_available:
            progress.messages.append(("system", "You have already used your Bonus Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={
                        "kind": "utilize",
                        "item_id": item.id,
                        "item_name": item.name,
                        "success": False,
                    },
                )
            )
            return

        healing_dice = _healing_potion_dice(item)
        if healing_dice is None:
            progress.messages.append(("system", f"{item.name} cannot be used that way yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={
                        "kind": "utilize",
                        "item_id": item.id,
                        "item_name": item.name,
                        "success": False,
                    },
                )
            )
            return

        dice_count, dice_sides, modifier = healing_dice
        dice_total = roll_dice(dice_count, dice_sides)
        healing_total = dice_total + modifier
        applied_healing = player.heal(healing_total)
        consumed = item.has_misc_tag("CNS")
        if consumed:
            player.inventory.remove_item(item.id)
        self.player_bonus_action_available = False

        modifier_text = f" + {modifier}" if modifier else ""
        progress.messages.extend(
            [
                ("system", f"{player.name} drinks {item.name}."),
                (
                    "system",
                    f"Healing: {dice_count}d{dice_sides}={dice_total}{modifier_text} "
                    f"= {healing_total}; applied {applied_healing}.",
                ),
            ]
        )
        if consumed:
            progress.messages.append(("system", f"{item.name} is consumed."))
        progress.events.append(
            self._event(
                "item_used",
                actor_ref="player",
                action_id=action_id,
                data={
                    "kind": "utilize",
                    "mode": "drink",
                    "item_id": item.id,
                    "item_name": item.name,
                    "target_ref": "player",
                    "target_label": player.name,
                    "success": True,
                    "consumed": consumed,
                    "effect": "healing",
                    "healing": applied_healing,
                    "healing_roll_detail": {
                        "dice": f"{dice_count}d{dice_sides}",
                        "dice_total": dice_total,
                        "modifier": modifier,
                        "total": healing_total,
                        "applied_healing": applied_healing,
                    },
                },
            )
        )

    def _resolve_feature_action(
        self,
        player: Actor,
        feature_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        feature_action = player.combat_profile.feature_actions.get(feature_id)
        if feature_action is None:
            progress.messages.append(("system", f"{feature_id} is not implemented yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        if feature_action.economy == "bonus_action" and not self.player_bonus_action_available:
            progress.messages.append(("system", "You have already used your Bonus Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return
        if feature_action.economy == "action" and not self.player_action_available:
            progress.messages.append(("system", "You have already used your Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return
        if feature_action.economy == "reaction" and not self.player_reaction_available:
            progress.messages.append(("system", "You have already used your Reaction."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        uses_remaining = player.feature_uses_remaining.get(feature_id, 0)
        if uses_remaining <= 0:
            progress.messages.append(
                ("system", f"You have no uses of {feature_action.label} remaining.")
            )
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        result = resolve_feature_action(player, feature_id, roll_dice)
        if result is None:
            progress.messages.append(("system", f"{feature_action.label} is not implemented yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        if feature_action.economy == "bonus_action":
            self.player_bonus_action_available = False
        elif feature_action.economy == "action":
            self.player_action_available = False
        elif feature_action.economy == "reaction":
            self.player_reaction_available = False

        progress.messages.extend(result.messages)
        healing_effect = next(
            (effect for effect in result.effects if effect.kind == "healing"),
            None,
        )
        healing_data = healing_effect.data if healing_effect is not None else {}
        healing_roll_detail = healing_data.get("roll", {})
        target_ref = healing_effect.target_ref if healing_effect is not None else "player"
        target_label = healing_data.get("target_label", player.name)
        healing = healing_data.get("amount", 0)
        progress.events.append(
            self._event(
                "feature_used",
                actor_ref="player",
                action_id=action_id,
                data={
                    "kind": "feature",
                    "feature_id": result.capability_id,
                    "feature_name": result.capability_name,
                    "target_ref": target_ref,
                    "target_label": target_label,
                    "success": True,
                    "healing": healing,
                    "healing_roll_detail": healing_roll_detail,
                    "uses_remaining": result.resource_updates.get(feature_id),
                    "effects": [
                        {
                            "kind": effect.kind,
                            "target_ref": effect.target_ref,
                            "success": effect.success,
                            "data": effect.data,
                        }
                        for effect in result.effects
                    ],
                },
            )
        )

    def _apply_player_move(
        self,
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

    def _queue_player_opportunity_attack(
        self,
        enemy_index: int,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: int,
        progress: EncounterProgress,
    ) -> bool:
        if not self.player_reaction_available:
            return False
        if not _is_adjacent(from_position, self.player_position):
            return False
        if _is_adjacent(to_position, self.player_position):
            return False

        frame_id = self._next_frame_id()
        trigger_id = self._next_frame_id(prefix="trigger")
        current_frame = self.current_decision()
        self.pending_action = PendingAction(
            id=action_id,
            kind="move",
            actor_ref=_enemy_ref(enemy_index),
            direction=direction,
            from_position=Position(from_position.x, from_position.y),
            to_position=Position(to_position.x, to_position.y),
            resume_enemy_index=enemy_index,
            remaining_movement_after=remaining_movement_after,
            trigger_id=trigger_id,
        )
        self.decision_stack.append(
            DecisionFrame(
                id=frame_id,
                actor_ref="player",
                kind="reaction",
                reason="opportunity_attack",
                parent_frame_id=current_frame.id,
                parent_action_id=action_id,
                can_pass=True,
            )
        )
        progress.events.append(
            self._event(
                "trigger_opened",
                actor_ref="player",
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "kind": "opportunity_attack",
                    "target_ref": _enemy_ref(enemy_index),
                    "trigger_id": trigger_id,
                },
            )
        )
        return True

    def _reaction_actions(self) -> list[EncounterAction]:
        pending_action = self.pending_action
        if pending_action is None or pending_action.kind != "move":
            return [
                EncounterAction(
                    "Pass reaction",
                    "pass",
                    id="player-reaction-pass",
                    actor_ref="player",
                    cost=ActionCost(),
                )
            ]

        target_index = _enemy_index(pending_action.actor_ref)
        target = self.enemies[target_index]
        actions: list[EncounterAction] = []
        if self.player_reaction_available and target.is_alive:
            actions.append(
                EncounterAction(
                    f"Opportunity attack {target.actor.name}",
                    "opportunity_attack",
                    target_index,
                    id=f"player-opportunity-attack-{target_index}",
                    actor_ref="player",
                    source_trigger_id=pending_action.trigger_id,
                    cost=ActionCost(reaction=1),
                )
            )
        actions.append(
            EncounterAction(
                "Pass reaction",
                "pass",
                id="player-reaction-pass",
                actor_ref="player",
                source_trigger_id=pending_action.trigger_id,
            )
        )
        return actions

    def _active_turn_actor(self) -> tuple[str, int | None]:
        self._normalize_turn()
        if self.turn_index == 0:
            return ("player", None)
        return ("enemy", self.turn_index - 1)

    def _check_transition(self) -> str | None:
        if all(not enemy.is_alive for enemy in self.enemies):
            return self.definition.victory.next_scene if self.definition.victory else None
        return None

    def _advance_turn(self) -> None:
        self.turn_index += 1
        if self.turn_index >= self._turn_count():
            self.turn_index = 0
            self.round_number += 1
        self._normalize_turn()
        if self.turn_index == 0:
            self.player_movement_remaining = None
            self.player_action_available = True
            self.player_attacks_remaining = 0
            self.player_bonus_action_available = True

    def _maybe_reset_reactions(self) -> None:
        if self.turn_index != 0:
            return
        self.player_reaction_available = True
        for enemy in self.enemies:
            enemy.reaction_available = True

    def _normalize_turn(self) -> None:
        if self.turn_index >= self._turn_count():
            self.turn_index = 0

        for _ in range(self._turn_count()):
            if self.turn_index == 0:
                return
            enemy = self.enemies[self.turn_index - 1]
            if enemy.is_alive:
                return
            self.turn_index += 1
            if self.turn_index >= self._turn_count():
                self.turn_index = 0
                self.round_number += 1

    def _player_movement_remaining(self, player: Actor) -> int:
        if self.player_movement_remaining is None:
            self.player_movement_remaining = _movement_squares(player)
        return self.player_movement_remaining

    def _turn_count(self) -> int:
        return len(self.enemies) + 1

    def _live_enemy_at(self, x: int, y: int) -> EncounterEnemyState | None:
        return next(
            (
                enemy
                for enemy in self.enemies
                if enemy.is_alive and enemy.position.x == x and enemy.position.y == y
            ),
            None,
        )

    def _is_free_for_enemy(self, x: int, y: int) -> bool:
        if not self._is_within_bounds(x, y):
            return False
        if self.player_position.x == x and self.player_position.y == y:
            return False
        return self._live_enemy_at(x, y) is None

    def _is_within_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.definition.grid.width and 0 <= y < self.definition.grid.height

    def _next_action_id(self) -> str:
        action_id = f"action_{self.action_sequence}"
        self.action_sequence += 1
        return action_id

    def _next_frame_id(self, prefix: str = "frame") -> str:
        frame_id = f"{prefix}_{self.frame_sequence}"
        self.frame_sequence += 1
        return frame_id

    def _event(
        self,
        event_type: str,
        actor_ref: ActorRef | None = None,
        frame_id: str | None = None,
        action_id: str | None = None,
        data: dict[str, object] | None = None,
    ) -> CombatEvent:
        event = CombatEvent(
            seq=self.event_sequence,
            type=event_type,
            actor_ref=actor_ref,
            frame_id=frame_id,
            action_id=action_id,
            data=data or {},
        )
        self.event_sequence += 1
        return event

    def _merge_progress(self, target: EncounterProgress, source: EncounterProgress) -> None:
        target.messages.extend(source.messages)
        target.events.extend(source.events)
        if source.transition is not None:
            target.transition = source.transition
        target.paused_for_decision = target.paused_for_decision or source.paused_for_decision

    def _export_pending_action(self) -> dict[str, object] | None:
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

    def _actor_label(self, actor_ref: ActorRef) -> str:
        if actor_ref == "player":
            return "Player"
        enemy_index = _enemy_index(actor_ref)
        enemy = self.enemies[enemy_index]
        return f"Enemy {enemy_index + 1} ({enemy.actor.name})"


def _build_behavior(enemy: EncounterEnemyState) -> Generator[EncounterAction | None, BehaviorContext, None]:
    if enemy.behavior.type == "guard":
        return _guard_behavior(enemy)
    if enemy.behavior.type == "patrol":
        return _patrol_behavior(enemy)
    return _chase_behavior(enemy)


def _chase_behavior(enemy: EncounterEnemyState) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack")
            continue

        direction = _step_toward(context.enemy_position, context.player_position)
        command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
        context = yield command


def _guard_behavior(enemy: EncounterEnemyState) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        anchor = enemy.behavior.anchor or enemy.position
        within_radius = (
            enemy.behavior.radius is not None
            and _manhattan_distance(context.player_position, anchor) <= enemy.behavior.radius
        )
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack")
            continue
        if within_radius:
            direction = _step_toward(context.enemy_position, context.player_position)
            command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
            context = yield command
            continue
        if context.enemy_position.x != anchor.x or context.enemy_position.y != anchor.y:
            direction = _step_toward(context.enemy_position, anchor)
            command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
            context = yield command
            continue
        context = yield EncounterAction("Wait", "wait")


def _patrol_behavior(enemy: EncounterEnemyState) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack")
            continue
        if not enemy.behavior.path:
            context = yield EncounterAction("Wait", "wait")
            continue
        enemy.patrol_index = (enemy.patrol_index + 1) % len(enemy.behavior.path)
        target = enemy.behavior.path[enemy.patrol_index]
        direction = _step_toward(context.enemy_position, target)
        command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
        context = yield command


def _step_toward(start: Position, target: Position) -> str | None:
    dx = target.x - start.x
    dy = target.y - start.y
    step_x = _sign(dx)
    step_y = _sign(dy)
    for direction, delta in DIRECTION_DELTAS.items():
        if delta == (step_x, step_y):
            return direction
    return None


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _is_adjacent(a: Position, b: Position) -> bool:
    return _chebyshev_distance(a, b) == 1


def _chebyshev_distance(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _manhattan_distance(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _movement_squares(actor: Actor) -> int:
    return actor.attributes.movement.squares_per_turn


def _healing_potions_in_inventory(actor: Actor, items_by_id: dict[str, Item]) -> list[Item]:
    seen: set[str] = set()
    potions: list[Item] = []
    for item_id in actor.inventory.items:
        if item_id in seen:
            continue
        seen.add(item_id)
        item = items_by_id.get(item_id)
        if item is not None and _healing_potion_dice(item) is not None:
            potions.append(item)
    return potions


def _healing_potion_dice(item: Item) -> tuple[int, int, int] | None:
    if not item.item_type.startswith("P"):
        return None
    if not item.has_misc_tag("CNS"):
        return None
    match = re.search(r"\{@dice\s+(\d+)d(\d+)(?:\s*\+\s*(\d+))?\}", item.description)
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _resolve_attack(
    attacker: Actor,
    defender: Actor,
    attacker_label: str,
    target_label: str,
    action_label: str = "Attack",
    items_by_id: dict[str, Item] | None = None,
) -> AttackOutcome:
    weapon = _equipped_weapon(attacker, items_by_id or {})
    ability_modifier = attacker.get_modifier(attacker.attributes.strength)
    proficiency_bonus = _weapon_proficiency_bonus(attacker, weapon)
    attack_modifier = ability_modifier + proficiency_bonus
    attack_die = roll_die(20)
    attack_roll = attack_die + attack_modifier
    target_ac = defender.get_armor_class()
    attack_roll_detail = {
        "die": attack_die,
        "ability_modifier": ability_modifier,
        "proficiency_bonus": proficiency_bonus,
        "modifier": attack_modifier,
        "total": attack_roll,
        "target_ac": target_ac,
    }
    if weapon is not None:
        attack_roll_detail["weapon_id"] = weapon.id
        attack_roll_detail["weapon_name"] = weapon.name
    action_prefix = action_label if action_label != "Attack" else "Attack"
    proficiency_text = (
        f" + proficiency {proficiency_bonus}" if proficiency_bonus else ""
    )
    attack_detail_message = (
        f"{action_prefix}: {attacker_label} attacks {target_label}. "
        f"Roll d20={attack_die} + STR mod {ability_modifier}{proficiency_text} "
        f"= {attack_roll} vs {target_label} AC {target_ac}."
    )
    if attack_roll < target_ac:
        return AttackOutcome(
            messages=[
                ("system", attack_detail_message),
                ("system", f"{attacker_label} misses {target_label}."),
            ],
            hit=False,
            attack_roll=attack_roll,
            damage=0,
            defender_defeated=False,
            attack_roll_detail=attack_roll_detail,
        )

    damage_dice = weapon.weapon_stat.damage if weapon and weapon.weapon_stat else "1d4"
    damage_die_count, damage_die_sides = _parse_damage_dice(damage_dice)
    damage_die_total = roll_dice(damage_die_count, damage_die_sides)
    damage_total = damage_die_total + ability_modifier
    damage = max(1, damage_total)
    applied_damage = defender.take_damage(damage)
    damage_roll_detail = {
        "dice": damage_dice,
        "dice_total": damage_die_total,
        "modifier": ability_modifier,
        "total": damage_total,
        "minimum_applied_total": damage,
        "applied_damage": applied_damage,
    }
    if weapon is not None:
        damage_roll_detail["weapon_id"] = weapon.id
        damage_roll_detail["weapon_name"] = weapon.name
    messages = [
        ("system", attack_detail_message),
        (
            "system",
            f"Damage to {target_label}: {damage_dice}={damage_die_total} "
            f"+ STR mod {ability_modifier} = {damage_total}; "
            f"final damage {damage}, applied {applied_damage}.",
        ),
        ("system", f"{attacker_label} hits {target_label} for {applied_damage} damage."),
    ]
    defeated = defender.get_health() <= 0
    if defeated:
        messages.append(("system", f"{target_label} is defeated."))
    return AttackOutcome(
        messages=messages,
        hit=True,
        attack_roll=attack_roll,
        damage=applied_damage,
        defender_defeated=defeated,
        attack_roll_detail=attack_roll_detail,
        damage_roll_detail=damage_roll_detail,
    )


def _equipped_weapon(attacker: Actor, items_by_id: dict[str, Item]) -> Item | None:
    for slot in ("right_hand", "left_hand"):
        item_id = attacker.equipment.equipped_items.get(slot)
        if item_id is None:
            continue
        item = items_by_id.get(item_id)
        if item is not None and item.weapon_stat is not None:
            return item
    return None


def _weapon_proficiency_bonus(attacker: Actor, weapon: Item | None) -> int:
    if weapon is None or weapon.weapon_stat is None:
        return 0
    weapon_proficiencies = attacker.attributes.proficiencies.get("weapons", [])
    if not isinstance(weapon_proficiencies, list):
        return 0
    category = weapon.weapon_stat.weapon_category
    is_proficient = (
        weapon.id in weapon_proficiencies
        or weapon.name.casefold() in {str(item).casefold() for item in weapon_proficiencies}
        or category in weapon_proficiencies
    )
    return attacker.attributes.proficiency_bonus if is_proficient else 0


def _parse_damage_dice(damage: str) -> tuple[int, int]:
    count_text, sides_text = damage.lower().split("d", 1)
    return int(count_text), int(sides_text)


def _enemy_ref(enemy_index: int) -> str:
    return f"enemy:{enemy_index}"


def _enemy_index(actor_ref: ActorRef) -> int:
    prefix = "enemy:"
    if not actor_ref.startswith(prefix):
        raise ValueError(f"'{actor_ref}' is not an enemy actor reference.")
    return int(actor_ref[len(prefix):])
