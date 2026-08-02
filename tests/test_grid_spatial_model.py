import pytest

from srd_arena.domain.geometry import (
    Grid,
    GridDistance,
    MovementBudget,
    MovementCost,
    Position,
    grid_distance_between,
)


def test_open_grid_range_counts_diagonals_as_one_square() -> None:
    distance = grid_distance_between(Position(1, 2), Position(5, 5))

    assert distance == 4
    assert isinstance(distance, GridDistance)


def test_grid_owns_feet_and_square_conversions() -> None:
    grid = Grid(width=10, height=10)

    assert grid.distance_from_feet(30) == GridDistance(6)
    assert grid.covering_distance_from_feet(7) == GridDistance(2)
    assert grid.feet_for_squares(6) == 30
    assert grid.movement_budget(30) == MovementBudget(6)


def test_movement_cost_and_budget_are_distinct_grid_quantities() -> None:
    assert MovementBudget(6) - MovementCost(2) == 4
    assert isinstance(MovementBudget(6), MovementBudget)
    assert isinstance(MovementCost(2), MovementCost)


def test_grid_rejects_invalid_dimensions_and_distances() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        Grid(width=0, height=10)
    with pytest.raises(ValueError, match="negative"):
        GridDistance(-1)
    with pytest.raises(ValueError, match="negative"):
        Grid(width=10, height=10).distance_from_feet(-5)
