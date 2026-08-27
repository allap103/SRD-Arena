"""Provide primitives support for the geometry package."""

from dataclasses import dataclass


class GridDistance(int):
    """A non-negative distance measured in grid cells."""

    def __new__(cls, squares: int) -> GridDistance:
        if squares < 0:
            raise ValueError("Grid distance cannot be negative.")
        return super().__new__(cls, squares)


class MovementBudget(int):
    """Movement available to spend, measured in grid cells."""

    def __new__(cls, squares: int) -> MovementBudget:
        if squares < 0:
            raise ValueError("Movement budget cannot be negative.")
        return super().__new__(cls, squares)


class MovementCost(int):
    """Movement required to enter one or more grid cells."""

    def __new__(cls, squares: int) -> MovementCost:
        if squares < 0:
            raise ValueError("Movement cost cannot be negative.")
        return super().__new__(cls, squares)


@dataclass
class Position:
    """Represent a position."""

    x: int
    y: int


@dataclass
class Grid:
    """Represent a grid."""

    width: int
    height: int
    square_size_feet: int = 5

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Grid dimensions must be positive.")
        if self.square_size_feet <= 0:
            raise ValueError("Grid square size must be positive.")

    def distance_between(self, a: Position, b: Position) -> GridDistance:
        """Return open-grid range, where diagonal and straight steps cost alike.

        >>> Grid(10, 10).distance_between(Position(1, 1), Position(4, 3))
        3
        """
        return grid_distance_between(a, b)

    def distance_from_feet(self, feet: int, *, minimum: int = 0) -> GridDistance:
        """Translate feet into complete grid cells, rounding down.

        >>> Grid(10, 10).distance_from_feet(17)
        3
        >>> Grid(10, 10).distance_from_feet(0, minimum=1)
        1
        """
        if feet < 0:
            raise ValueError("Distance in feet cannot be negative.")
        return GridDistance(max(minimum, feet // self.square_size_feet))

    def covering_distance_from_feet(self, feet: int) -> GridDistance:
        """Translate an extent in feet into cells, rounding up.

        >>> Grid(10, 10).covering_distance_from_feet(17)
        4
        """
        if feet < 0:
            raise ValueError("Distance in feet cannot be negative.")
        return GridDistance((feet + self.square_size_feet - 1) // self.square_size_feet)

    def movement_budget(self, speed_feet: int) -> MovementBudget:
        """Convert a creature's speed into spendable grid cells.

        >>> Grid(10, 10).movement_budget(30)
        6
        """
        return MovementBudget(self.distance_from_feet(speed_feet))

    def feet_for_squares(self, squares: int) -> int:
        """Convert grid cells into their represented distance in feet.

        >>> Grid(10, 10).feet_for_squares(6)
        30
        """
        if squares < 0:
            raise ValueError("Grid squares cannot be negative.")
        return squares * self.square_size_feet


def manhattan_distance(a: Position, b: Position) -> GridDistance:
    """Return the orthogonal-only distance between two positions.

    >>> manhattan_distance(Position(1, 1), Position(4, 3))
    5
    """

    return GridDistance(abs(a.x - b.x) + abs(a.y - b.y))


def grid_distance_between(a: Position, b: Position) -> GridDistance:
    """Return square-grid distance with equal diagonal and straight costs.

    >>> grid_distance_between(Position(1, 1), Position(4, 3))
    3
    """

    return GridDistance(max(abs(a.x - b.x), abs(a.y - b.y)))
