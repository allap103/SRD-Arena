from game.encounter_geometry import (
    build_cone_area,
    build_cube_area,
    build_line_area,
    build_radius_area,
)
from game.models.scene import Grid, Position


def _coords(area) -> set[tuple[int, int]]:
    return {(cell.x, cell.y) for cell in area.cells}


def test_radius_area_includes_chebyshev_cells_within_bounds() -> None:
    area = build_radius_area(Position(2, 2), 1, Grid(width=5, height=5))

    assert area.shape == "radius"
    assert area.origin == Position(2, 2)
    assert _coords(area) == {
        (1, 1),
        (2, 1),
        (3, 1),
        (1, 2),
        (2, 2),
        (3, 2),
        (1, 3),
        (2, 3),
        (3, 3),
    }


def test_radius_area_clips_at_grid_edges() -> None:
    area = build_radius_area(Position(0, 0), 1, Grid(width=3, height=3))

    assert _coords(area) == {
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
    }


def test_cone_area_widens_each_step_for_cardinal_direction() -> None:
    area = build_cone_area(Position(3, 4), "up", 3, Grid(width=7, height=7))

    assert area.shape == "cone"
    assert _coords(area) == {
        (3, 3),
        (2, 2),
        (3, 2),
        (4, 2),
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (5, 1),
    }


def test_cone_area_supports_diagonal_direction() -> None:
    area = build_cone_area(Position(2, 4), "up-right", 3, Grid(width=7, height=7))

    assert _coords(area) == {
        (3, 3),
        (3, 2),
        (4, 2),
        (4, 3),
        (3, 1),
        (4, 1),
        (5, 1),
        (5, 2),
        (5, 3),
    }


def test_line_area_follows_cardinal_direction() -> None:
    area = build_line_area(Position(2, 4), "up", 3, Grid(width=7, height=7))

    assert area.shape == "line"
    assert _coords(area) == {
        (2, 3),
        (2, 2),
        (2, 1),
    }


def test_line_area_supports_diagonal_direction() -> None:
    area = build_line_area(Position(2, 4), "up-right", 3, Grid(width=7, height=7))

    assert _coords(area) == {
        (3, 3),
        (4, 2),
        (5, 1),
    }


def test_cube_area_extends_away_from_origin_for_cardinal_direction() -> None:
    area = build_cube_area(Position(3, 4), "up", 3, Grid(width=7, height=7))

    assert area.shape == "cube"
    assert _coords(area) == {
        (2, 1),
        (3, 1),
        (4, 1),
        (2, 2),
        (3, 2),
        (4, 2),
        (2, 3),
        (3, 3),
        (4, 3),
    }


def test_cube_area_supports_diagonal_direction() -> None:
    area = build_cube_area(Position(2, 4), "up-right", 3, Grid(width=7, height=7))

    assert _coords(area) == {
        (3, 1),
        (4, 1),
        (5, 1),
        (3, 2),
        (4, 2),
        (5, 2),
        (3, 3),
        (4, 3),
        (5, 3),
    }
