from __future__ import annotations

from typing import Generator

from ..creatures import Creature
from ..equipment import Item
from ..geometry import Position
from .models import BehaviorContext, EncounterAction, EncounterCreatureState

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


def build_behavior(
    participant: EncounterCreatureState,
    items_by_id: dict[str, Item],
) -> Generator[EncounterAction | None, BehaviorContext, None]:
    if participant.behavior.type == "wait":
        return _wait_behavior()
    if participant.behavior.type == "archer":
        return _archer_behavior(participant, items_by_id)
    if participant.behavior.type == "guard":
        return _guard_behavior(participant)
    if participant.behavior.type == "patrol":
        return _patrol_behavior(participant)
    return _chase_behavior(participant)


def _wait_behavior() -> Generator[EncounterAction | None, BehaviorContext, None]:
    yield None
    while True:
        yield EncounterAction("Wait", "wait")


def _chase_behavior(
    participant: EncounterCreatureState,
) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack", "melee")
            continue
        direction = step_toward(context.actor_position, context.target_position)
        command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
        context = yield command


def _archer_behavior(
    participant: EncounterCreatureState,
    items_by_id: dict[str, Item],
) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        range_squares = weapon_normal_range_squares(participant.creature, items_by_id)
        if range_squares is not None and chebyshev_distance(
            context.actor_position,
            context.target_position,
        ) <= range_squares:
            context = yield EncounterAction("Attack", "attack", "ranged")
            continue
        direction = step_toward(context.actor_position, context.target_position)
        command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
        context = yield command


def _guard_behavior(
    participant: EncounterCreatureState,
) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        anchor = participant.behavior.anchor or participant.position
        within_radius = (
            participant.behavior.radius is not None
            and manhattan_distance(context.target_position, anchor) <= participant.behavior.radius
        )
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack", "melee")
            continue
        if within_radius:
            direction = step_toward(context.actor_position, context.target_position)
            command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
            context = yield command
            continue
        if context.actor_position.x != anchor.x or context.actor_position.y != anchor.y:
            direction = step_toward(context.actor_position, anchor)
            command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
            context = yield command
            continue
        context = yield EncounterAction("Wait", "wait")


def _patrol_behavior(
    participant: EncounterCreatureState,
) -> Generator[EncounterAction | None, BehaviorContext, None]:
    context = yield None
    while True:
        if context.can_attack:
            context = yield EncounterAction("Attack", "attack", "melee")
            continue
        if not participant.behavior.path:
            context = yield EncounterAction("Wait", "wait")
            continue
        participant.patrol_index = (participant.patrol_index + 1) % len(participant.behavior.path)
        target = participant.behavior.path[participant.patrol_index]
        direction = step_toward(context.actor_position, target)
        command = EncounterAction("Move", "move", direction) if direction else EncounterAction("Wait", "wait")
        context = yield command


def step_toward(start: Position, target: Position) -> str | None:
    dx = sign(target.x - start.x)
    dy = sign(target.y - start.y)
    for direction, (delta_x, delta_y) in DIRECTION_DELTAS.items():
        if (dx, dy) == (delta_x, delta_y):
            return direction
    return None


def sign(value: int) -> int:
    if value < 0:
        return -1
    if value > 0:
        return 1
    return 0


def is_adjacent(a: Position, b: Position) -> bool:
    return chebyshev_distance(a, b) == 1


def chebyshev_distance(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def manhattan_distance(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def movement_squares(creature: Creature) -> int:
    return creature.attributes.movement.squares_per_turn


def weapon_normal_range_squares(attacker: Creature, items_by_id: dict[str, Item]) -> int | None:
    for slot in ("right_hand", "left_hand"):
        item_id = attacker.equipment.equipped_items.get(slot)
        if item_id is None:
            continue
        weapon = items_by_id.get(item_id)
        if weapon is None or weapon.weapon_stat is None:
            continue
        if weapon.weapon_stat.range_normal is None:
            return None
        return max(1, weapon.weapon_stat.range_normal // attacker.attributes.movement.feet_per_square)
    for attack in attacker.monster_attacks:
        if "ranged" not in attack.attack_modes or attack.range_normal is None:
            continue
        return max(1, attack.range_normal // attacker.attributes.movement.feet_per_square)
    return None
