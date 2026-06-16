from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Generator

from .models.actor import Actor
from .models.scene import Behavior, Encounter, Position
from .systems.roll import roll_dice, roll_die


@dataclass
class EncounterAction:
    label: str
    kind: str
    value: str | int | None = None


@dataclass
class BehaviorContext:
    player_position: Position
    enemy_position: Position
    can_attack: bool


@dataclass
class EncounterEnemyState:
    actor_id: str
    actor: Actor
    position: Position
    behavior: Behavior
    patrol_index: int = 0

    @property
    def is_alive(self) -> bool:
        return self.actor.get_health() > 0


@dataclass
class EncounterSnapshotEnemy:
    actor_id: str
    current_health: int
    position: Position
    patrol_index: int = 0


@dataclass
class EncounterSnapshot:
    scene_id: str
    player_position: Position
    enemies: list[EncounterSnapshotEnemy] = field(default_factory=list)


@dataclass
class EncounterState:
    scene_id: str
    definition: Encounter
    player_position: Position
    enemies: list[EncounterEnemyState]
    _behaviors: list[Generator] = field(default_factory=list, repr=False)

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
                )
            )
        state = cls(
            scene_id=snapshot.scene_id,
            definition=definition,
            player_position=Position(snapshot.player_position.x, snapshot.player_position.y),
            enemies=enemies,
        )
        state._initialize_behaviors()
        return state

    def snapshot(self) -> EncounterSnapshot:
        return EncounterSnapshot(
            scene_id=self.scene_id,
            player_position=Position(self.player_position.x, self.player_position.y),
            enemies=[
                EncounterSnapshotEnemy(
                    actor_id=enemy.actor_id,
                    current_health=enemy.actor.get_health(),
                    position=Position(enemy.position.x, enemy.position.y),
                    patrol_index=enemy.patrol_index,
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
        rows = []
        for y in range(self.definition.grid.height):
            row = []
            for x in range(self.definition.grid.width):
                if self.player_position.x == x and self.player_position.y == y:
                    row.append("P")
                    continue
                live_enemy = next(
                    (
                        enemy
                        for enemy in self.enemies
                        if enemy.is_alive and enemy.position.x == x and enemy.position.y == y
                    ),
                    None,
                )
                row.append("E" if live_enemy else ".")
            rows.append(" ".join(row))

        enemy_lines = [
            f"- Enemy {index + 1} ({enemy.actor.name}): {enemy.actor.get_health()} HP at ({enemy.position.x}, {enemy.position.y})"
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
        ]
        if not enemy_lines:
            enemy_lines = ["- No enemies remaining."]

        return "\n".join(
            [
                *rows,
                "",
                f"Player HP: {player.get_health()}/{player.get_max_health()} at ({self.player_position.x}, {self.player_position.y})",
                "Enemies:",
                *enemy_lines,
            ]
        )

    def available_actions(self) -> list[EncounterAction]:
        actions = []
        for direction, dx, dy in (
            ("up", 0, -1),
            ("down", 0, 1),
            ("left", -1, 0),
            ("right", 1, 0),
        ):
            target_x = self.player_position.x + dx
            target_y = self.player_position.y + dy
            if not self._is_within_bounds(target_x, target_y):
                continue
            if self._live_enemy_at(target_x, target_y) is not None:
                continue
            actions.append(EncounterAction(f"Move {direction}", "move", direction))

        for index, enemy in enumerate(self.enemies):
            if enemy.is_alive and _distance(self.player_position, enemy.position) == 1:
                actions.append(
                    EncounterAction(
                        f"Attack enemy {index + 1} ({enemy.actor.name})",
                        "attack",
                        index,
                    )
                )

        actions.append(EncounterAction("Wait", "wait"))

        if self.definition.flee and self.definition.flee.allowed:
            actions.append(EncounterAction("Flee encounter", "flee"))

        return actions

    def apply_action(self, player: Actor, action: EncounterAction) -> tuple[list[tuple[str, str]], str | None]:
        messages: list[tuple[str, str]] = []
        transition: str | None = None

        if action.kind == "move":
            direction = str(action.value)
            dx, dy = {
                "up": (0, -1),
                "down": (0, 1),
                "left": (-1, 0),
                "right": (1, 0),
            }[direction]
            self.player_position = Position(
                self.player_position.x + dx,
                self.player_position.y + dy,
            )
            messages.append(("system", f"You move {direction}."))
        elif action.kind == "attack":
            enemy = self.enemies[int(action.value)]
            messages.extend(_resolve_attack(player, enemy.actor, f"Enemy {int(action.value) + 1}"))
            if not enemy.is_alive:
                messages.append(("system", f"Enemy {int(action.value) + 1} falls."))
        elif action.kind == "wait":
            messages.append(("system", "You hold your ground."))
        elif action.kind == "flee":
            messages.append(("system", "You flee the encounter."))
            return messages, self.definition.flee.next_scene if self.definition.flee else None

        transition = self._check_transition()
        if transition is not None:
            return messages, transition

        messages.extend(self.advance_enemies(player))
        transition = self._check_transition()
        return messages, transition

    def advance_enemies(self, player: Actor) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = []
        for enemy, behavior in zip(self.enemies, self._behaviors, strict=False):
            if not enemy.is_alive:
                continue
            if player.get_health() <= 0:
                break

            command = behavior.send(
                BehaviorContext(
                    player_position=Position(self.player_position.x, self.player_position.y),
                    enemy_position=Position(enemy.position.x, enemy.position.y),
                    can_attack=_distance(self.player_position, enemy.position) == 1,
                )
            )

            if command.kind == "move":
                direction = str(command.value)
                dx, dy = {
                    "up": (0, -1),
                    "down": (0, 1),
                    "left": (-1, 0),
                    "right": (1, 0),
                }[direction]
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                if self._is_free_for_enemy(target_x, target_y):
                    enemy.position = Position(target_x, target_y)
                    messages.append(
                        (
                            "system",
                            f"{enemy.actor.name} moves {direction} to ({target_x}, {target_y}).",
                        )
                    )
            elif command.kind == "attack":
                messages.extend(_resolve_attack(enemy.actor, player, enemy.actor.name))
            else:
                messages.append(("system", f"{enemy.actor.name} waits."))
        return messages

    def _check_transition(self) -> str | None:
        if all(not enemy.is_alive for enemy in self.enemies):
            return self.definition.victory.next_scene if self.definition.victory else None
        return None

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
        command = (
            EncounterAction("Move", "move", direction)
            if direction
            else EncounterAction("Wait", "wait")
        )
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
            command = (
                EncounterAction("Move", "move", direction)
                if direction
                else EncounterAction("Wait", "wait")
            )
            context = yield command
            continue
        if context.enemy_position.x != anchor.x or context.enemy_position.y != anchor.y:
            direction = _step_toward(context.enemy_position, anchor)
            command = (
                EncounterAction("Move", "move", direction)
                if direction
                else EncounterAction("Wait", "wait")
            )
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
        command = (
            EncounterAction("Move", "move", direction)
            if direction
            else EncounterAction("Wait", "wait")
        )
        context = yield command


def _step_toward(start: Position, target: Position) -> str | None:
    dx = target.x - start.x
    dy = target.y - start.y
    if dx > 0:
        return "right"
    if dx < 0:
        return "left"
    if dy > 0:
        return "down"
    if dy < 0:
        return "up"
    return None


def _distance(a: Position, b: Position) -> int:
    return _manhattan_distance(a, b)


def _manhattan_distance(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _resolve_attack(attacker: Actor, defender: Actor, attacker_name: str) -> list[tuple[str, str]]:
    attack_roll = roll_die(20) + attacker.get_modifier(attacker.attributes.strength)
    if attack_roll < defender.get_armor_class():
        return [("system", f"{attacker_name} misses.")]

    damage = max(1, roll_dice(1, 4) + attacker.get_modifier(attacker.attributes.strength))
    applied_damage = defender.take_damage(damage)
    messages = [("system", f"{attacker_name} hits for {applied_damage} damage.")]
    if defender.get_health() <= 0:
        messages.append(("system", f"{defender.name} is defeated."))
    return messages
