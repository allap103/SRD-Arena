from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Generator

from .models.actor import Actor
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


@dataclass
class EncounterState:
    scene_id: str
    definition: Encounter
    player_position: Position
    enemies: list[EncounterEnemyState]
    turn_index: int = 0
    round_number: int = 1
    player_movement_remaining: int | None = None
    player_reaction_available: bool = True
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    decision_stack: list[DecisionFrame] = field(default_factory=list)
    pending_action: PendingAction | None = None
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
        )
        state._initialize_behaviors()
        return state

    @classmethod
    def from_snapshot(
        cls,
        definition: Encounter,
        snapshot: EncounterSnapshot,
        actor_templates: dict[str, Actor],
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
            "round_number": self.round_number,
            "turn_index": self.turn_index,
            "player": {
                "position": {"x": self.player_position.x, "y": self.player_position.y},
                "health": player.get_health(),
                "max_health": player.get_max_health(),
                "movement_remaining": self._player_movement_remaining(player),
                "reaction_available": self.player_reaction_available,
            },
            "enemies": [
                {
                    "actor_ref": _enemy_ref(index),
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

        for index, enemy in enumerate(self.enemies):
            if enemy.is_alive and _is_adjacent(self.player_position, enemy.position):
                actions.append(
                    EncounterAction(
                        f"Attack enemy {index + 1} ({enemy.actor.name})",
                        "attack",
                        index,
                        id=f"player-attack-{index}",
                        actor_ref="player",
                        cost=ActionCost(action=1),
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
        action_ends_turn = True

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
                action_ends_turn = False
        elif action.kind == "attack":
            if not isinstance(action.value, int):
                raise ValueError(
                    f"Encounter attack action requires an integer target, got {action.value!r}."
                )
            enemy_index = action.value
            enemy = self.enemies[enemy_index]
            attack = _resolve_attack(player, enemy.actor, f"Enemy {enemy_index + 1}")
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={
                        "target_ref": _enemy_ref(enemy_index),
                        "attack_roll": attack.attack_roll,
                        "hit": attack.hit,
                        "damage": attack.damage,
                    },
                )
            )
            if not enemy.is_alive:
                progress.messages.append(("system", f"Enemy {enemy_index + 1} falls."))
                progress.events.append(
                    self._event(
                        "actor_defeated",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind == "wait":
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
                attack = _resolve_attack(enemy.actor, player, enemy.actor.name)
                progress.messages.extend(attack.messages)
                progress.events.append(
                    self._event(
                        "attack_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "target_ref": "player",
                            "attack_roll": attack.attack_roll,
                            "hit": attack.hit,
                            "damage": attack.damage,
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
            attack = _resolve_attack(player, target.actor, "Opportunity attack")
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    frame_id=decision.id,
                    action_id=resolved_action_id,
                    data={
                        "target_ref": pending_action.actor_ref,
                        "attack_roll": attack.attack_roll,
                        "hit": attack.hit,
                        "damage": attack.damage,
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
            attack = _resolve_attack(enemy.actor, player, f"{enemy.actor.name} opportunity attack")
            messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref=_enemy_ref(index),
                    action_id=action_id,
                    data={
                        "target_ref": "player",
                        "attack_roll": attack.attack_roll,
                        "hit": attack.hit,
                        "damage": attack.damage,
                        "reaction": True,
                    },
                )
            )
            if player.get_health() <= 0:
                break
        return messages

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


def _resolve_attack(attacker: Actor, defender: Actor, attacker_name: str) -> AttackOutcome:
    attack_roll = roll_die(20) + attacker.get_modifier(attacker.attributes.strength)
    if attack_roll < defender.get_armor_class():
        return AttackOutcome(
            messages=[("system", f"{attacker_name} misses.")],
            hit=False,
            attack_roll=attack_roll,
            damage=0,
            defender_defeated=False,
        )

    damage = max(1, roll_dice(1, 4) + attacker.get_modifier(attacker.attributes.strength))
    applied_damage = defender.take_damage(damage)
    messages = [("system", f"{attacker_name} hits for {applied_damage} damage.")]
    defeated = defender.get_health() <= 0
    if defeated:
        messages.append(("system", f"{defender.name} is defeated."))
    return AttackOutcome(
        messages=messages,
        hit=True,
        attack_roll=attack_roll,
        damage=applied_damage,
        defender_defeated=defeated,
    )


def _enemy_ref(enemy_index: int) -> str:
    return f"enemy:{enemy_index}"


def _enemy_index(actor_ref: ActorRef) -> int:
    prefix = "enemy:"
    if not actor_ref.startswith(prefix):
        raise ValueError(f"'{actor_ref}' is not an enemy actor reference.")
    return int(actor_ref[len(prefix):])
