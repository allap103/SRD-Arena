"""Answer sight questions without conflating obscuration with physical cover."""

from __future__ import annotations

from srd_arena.domain.geometry import Position

from ..encounter_models.actions import CreatureRef
from ..spatial import creature_occupied_cells, minimum_cell_distance
from .context import VisibilityQueryContext
from .obstructions import cell_has_line_of_effect, grid_ray_cells
from .senses import sense_range


def creature_can_see_creature(
    state: VisibilityQueryContext,
    viewer_ref: CreatureRef,
    subject_ref: CreatureRef,
) -> bool:
    """Return whether any footprint ray lets the viewer perceive the subject."""

    subject_cells = creature_occupied_cells(state, subject_ref)
    return any(
        creature_can_see_cell(state, viewer_ref, subject) for subject in subject_cells
    )


def creature_can_see_cell(
    state: VisibilityQueryContext,
    viewer_ref: CreatureRef,
    subject: Position,
) -> bool:
    """Return whether terrain, obscuration, and Blindsight allow perception."""

    viewer_cells = creature_occupied_cells(state, viewer_ref)
    clear_rays = tuple(
        (viewer, grid_ray_cells(viewer, subject))
        for viewer in viewer_cells
        if cell_has_line_of_effect(state, viewer, subject)
    )
    if not clear_rays:
        return False
    if any(
        not any(_cell_is_heavily_obscured(state, cell) for cell in ray)
        for _viewer, ray in clear_rays
    ):
        return True
    blindsight = sense_range(state, viewer_ref, "blindsight").range_feet or 0
    if blindsight <= 0:
        return False
    distance = minimum_cell_distance(viewer_cells, (subject,))
    return state.definition.grid.feet_for_squares(distance) <= blindsight


def _cell_is_heavily_obscured(
    state: VisibilityQueryContext,
    cell: Position,
) -> bool:
    """Return whether an active persistent area heavily obscures one cell."""

    return any(
        effect.obscures_vision
        and effect.area is not None
        and any(
            area_cell.x == cell.x and area_cell.y == cell.y
            for area_cell in effect.area.cells
        )
        for effect in state.ongoing_effects
    )
