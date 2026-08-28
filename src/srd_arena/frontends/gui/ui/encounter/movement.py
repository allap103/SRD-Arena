"""Plan movement previews from frontend encounter views."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ...presentation.models import BattlefieldView, EncounterView

GridCell = tuple[int, int]
MovementPath = tuple[str, ...]

MOVE_DELTAS = {
    "up-left": (-1, -1),
    "up": (0, -1),
    "up-right": (1, -1),
    "left": (-1, 0),
    "right": (1, 0),
    "down-left": (-1, 1),
    "down": (0, 1),
    "down-right": (1, 1),
}
MOVEMENT_PATH_DIRECTIONS = (
    "up",
    "right",
    "down",
    "left",
    "up-right",
    "down-right",
    "down-left",
    "up-left",
)


@dataclass(frozen=True)
class MovementPlan:
    """The currently previewed paths for one active creature."""

    creature_ref: str
    paths: dict[GridCell, MovementPath]

    def path_to(self, destination: GridCell) -> MovementPath | None:
        """Return the previewed path to a destination, if one exists.

        >>> plan = MovementPlan("hero", {(1, 1): ("right", "down")})
        >>> plan.path_to((1, 1))
        ('right', 'down')
        >>> plan.path_to((9, 9)) is None
        True
        """

        return self.paths.get(destination)


def build_movement_plan(
    encounter: EncounterView,
    creature_ref: str,
) -> MovementPlan | None:
    """Build a movement preview for an active creature that can still move.

    >>> from types import SimpleNamespace
    >>> hero = SimpleNamespace(
    ...     creature_ref="hero", is_active=True,
    ...     position=SimpleNamespace(x=0, y=0),
    ... )
    >>> action = SimpleNamespace(cost={"movement": 1})
    >>> encounter = SimpleNamespace(
    ...     battlefield=SimpleNamespace(width=3, height=3, creatures=[hero]),
    ...     movement_actions={"right": action},
    ...     resources=SimpleNamespace(movement_remaining=2),
    ... )
    >>> plan = build_movement_plan(encounter, "hero")
    >>> plan.path_to((2, 0)) if plan else None
    ('right', 'right')
    """

    planner = next(
        (
            creature
            for creature in encounter.battlefield.creatures
            if creature.creature_ref == creature_ref and creature.is_active
        ),
        None,
    )
    movement_costs = [
        action.cost.get("movement", 0)
        for action in encounter.movement_actions.values()
        if action.cost.get("movement", 0) > 0
    ]
    if planner is None or not movement_costs:
        return None

    step_cost = min(movement_costs)
    max_steps = encounter.resources.movement_remaining // step_cost
    blocked = {
        (creature.position.x, creature.position.y)
        for creature in encounter.battlefield.creatures
        if creature.creature_ref != creature_ref
    }
    origin = (planner.position.x, planner.position.y)
    return MovementPlan(
        creature_ref=creature_ref,
        paths=shortest_movement_paths(
            encounter.battlefield.width,
            encounter.battlefield.height,
            origin,
            blocked,
            max_steps,
        ),
    )


def movement_plan_is_current(
    plan: MovementPlan | None,
    battlefield: BattlefieldView,
) -> bool:
    """Return whether a plan still belongs to the active battlefield creature.

    >>> from types import SimpleNamespace
    >>> battlefield = SimpleNamespace(creatures=[
    ...     SimpleNamespace(creature_ref="hero", is_active=True)
    ... ])
    >>> movement_plan_is_current(MovementPlan("hero", {}), battlefield)
    True
    >>> movement_plan_is_current(MovementPlan("goblin", {}), battlefield)
    False
    """

    if plan is None:
        return True
    return any(
        creature.creature_ref == plan.creature_ref and creature.is_active
        for creature in battlefield.creatures
    )


def shortest_movement_paths(
    width: int,
    height: int,
    origin: GridCell,
    blocked: set[GridCell],
    max_steps: int,
) -> dict[GridCell, MovementPath]:
    """Find one shortest path to every reachable grid cell.

    >>> paths = shortest_movement_paths(3, 1, (0, 0), {(1, 0)}, 3)
    >>> paths
    {(0, 0): ()}
    >>> shortest_movement_paths(3, 1, (0, 0), set(), 2)[(2, 0)]
    ('right', 'right')
    """

    paths: dict[GridCell, MovementPath] = {origin: ()}
    frontier = deque([origin])
    while frontier:
        position = frontier.popleft()
        path = paths[position]
        if len(path) >= max_steps:
            continue
        for direction in MOVEMENT_PATH_DIRECTIONS:
            delta_x, delta_y = MOVE_DELTAS[direction]
            destination = (
                position[0] + delta_x,
                position[1] + delta_y,
            )
            if (
                destination in paths
                or destination in blocked
                or not 0 <= destination[0] < width
                or not 0 <= destination[1] < height
            ):
                continue
            paths[destination] = (*path, direction)
            frontier.append(destination)
    return paths
