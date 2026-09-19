"""Validate spell coordinates independently of the area's current occupants."""

from math import isfinite
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import Position

from ...spatial import creature_occupied_cells
from ..option_discovery.spell_areas import spell_area
from ..option_discovery.spellcasting import spell_range_squares_for
from .models import EligibilityFailure

if TYPE_CHECKING:
    from srd_arena.domain.spells import Spell

    from ...encounter import EncounterState


def spell_aim_failure(
    state: EncounterState,
    actor_ref: str,
    spell: Spell,
    aim: tuple[float, float] | None,
) -> EligibilityFailure | None:
    """Check finite coordinates, board bounds, point range, and area construction."""
    if aim is None:
        return None
    if len(aim) != 2 or any(
        not isinstance(v, (int, float)) or not isfinite(v) for v in aim
    ):
        return EligibilityFailure(
            "invalid_aim", "An aim must contain two finite coordinates."
        )
    if spell.geometry_mode not in {"point_area", "directional_area"}:
        return None
    grid = state.definition.grid
    if not (0 <= aim[0] < grid.width and 0 <= aim[1] < grid.height):
        return EligibilityFailure(
            "aim_out_of_bounds", "The aim must be on the battlefield."
        )
    actor = state.creatures[actor_ref].creature
    if spell.geometry_mode == "point_area":
        maximum = spell_range_squares_for(state, spell, actor)
        position = Position(int(aim[0]), int(aim[1]))
        if (
            maximum is not None
            and min(
                grid.distance_between(cell, position)
                for cell in creature_occupied_cells(state, actor_ref)
            )
            > maximum
        ):
            return EligibilityFailure(
                "aim_out_of_range", "The chosen point is out of range."
            )
    if spell_area(state, actor, spell, aim_point=aim) is None:
        return EligibilityFailure(
            "invalid_aim", "The aim does not define a spell area."
        )
    return None
