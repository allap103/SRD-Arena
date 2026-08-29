"""Construct spell areas and resolve the creatures whose footprints intersect them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.geometry import (
    AreaOfEffect,
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    vector_between_positions,
)
from srd_arena.domain.spells.definitions import Spell
from srd_arena.domain.spells.resolution import SpellTargetContext
from srd_arena.domain.spells.rules import spell_area_shape

from ...state_runtime import creature_position
from .spell_targets import spell_target_context
from .spellcasting import spell_range_squares_for

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_area_targets(
    state: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> tuple[SpellTargetContext, ...]:
    """Return legal creature targets intersected by an aimed spell area.

    A direct spell with no constructed area falls back to its selected target.

    >>> from types import SimpleNamespace
    >>> target = SimpleNamespace(target_ref="goblin")
    >>> state = SimpleNamespace()
    >>> spell = Spell("bolt", "Bolt", None, 0)
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_areas."
    ...     "spell_area", return_value=None
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_areas."
    ...     "spell_target_context", return_value=target
    ... ):
    ...     targets = spell_area_targets(
    ...         state, SimpleNamespace(), spell, target_ref="goblin"
    ...     )
    >>> targets
    (namespace(target_ref='goblin'),)
    """

    area = spell_area(state, actor, spell, target_ref=target_ref, aim_point=aim_point)
    if area is None:
        if target_ref is None:
            return ()
        target = spell_target_context(state, actor, target_ref)
        return (target,) if target is not None else ()
    return tuple(targets_in_area(state, actor, area))


def spell_area(
    state: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> AreaOfEffect | None:
    """Construct the continuous and rasterized area for an aimed spell.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.geometry import Grid
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="mage"),
    ...     creatures={"mage": SimpleNamespace(position=Position(0, 0))},
    ...     definition=SimpleNamespace(grid=Grid(10, 10)),
    ... )
    >>> spell = Spell(
    ...     "fireball", "Fireball", None, 3,
    ...     geometry_mode="point_area", area_size_feet=20,
    ... )
    >>> area = spell_area(state, SimpleNamespace(), spell, aim_point=(5, 5))
    >>> (area.origin, bool(area.cells)) if area else None
    (Position(x=5, y=5), True)
    """

    creature_ref = state.current_decision().creature_ref
    actor_position = creature_position(state, creature_ref)
    if spell.geometry_mode == "point_area":
        if aim_point is None:
            return None
        radius_feet = spell.area_size_feet
        if radius_feet is None:
            return None
        radius_squares = int(
            state.definition.grid.distance_from_feet(radius_feet, minimum=1)
        )
        origin = Position(int(aim_point[0]), int(aim_point[1]))
        if spell_area_shape(spell) == "cube":
            return build_point_cube_area(origin, radius_squares, state.definition.grid)
        return build_radius_area(origin, radius_squares, state.definition.grid)
    if spell.geometry_mode != "directional_area":
        return None
    if aim_point is not None:
        if (
            abs(aim_point[0] - (actor_position.x + 0.5)) < 1e-9
            and abs(aim_point[1] - (actor_position.y + 0.5)) < 1e-9
        ):
            return None
        direction = Vector2D(
            aim_point[0] - (actor_position.x + 0.5),
            aim_point[1] - (actor_position.y + 0.5),
        )
    else:
        if target_ref is None:
            return None
        target = spell_target_context(state, actor, target_ref)
        if target is None or target_ref == creature_ref:
            return None
        direction = vector_between_positions(
            actor_position,
            creature_position(state, target_ref),
        )
    length = spell_range_squares_for(state, spell, actor)
    if length is None:
        return None
    coverage_threshold = state.geometry_config.directional_area_cell_coverage_threshold
    return build_directional_area(
        spell.range.kind if spell.range is not None else None,
        actor_position,
        direction,
        length,
        state.definition.grid,
        coverage_threshold=coverage_threshold,
    )


def targets_in_area(
    state: EncounterState,
    actor: Creature,
    area: AreaOfEffect,
) -> list[SpellTargetContext]:
    """Return living creature references whose footprints intersect affected cells.

    >>> from types import SimpleNamespace
    >>> area = AreaOfEffect("sphere", Position(0, 0), (Position(1, 1),))
    >>> target = SimpleNamespace(target_ref="goblin")
    >>> state = SimpleNamespace(
    ...     creatures={
    ...         "goblin": SimpleNamespace(is_alive=True, position=Position(1, 1)),
    ...         "fallen": SimpleNamespace(is_alive=False, position=Position(1, 1)),
    ...     },
    ... )
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_areas."
    ...     "spell_target_context", return_value=target
    ... ):
    ...     targets = targets_in_area(state, SimpleNamespace(), area)
    >>> targets
    [namespace(target_ref='goblin')]
    """

    occupied_cells = {(cell.x, cell.y) for cell in area.cells}
    targets: list[SpellTargetContext] = []
    for target_ref, target_state in state.creatures.items():
        if not target_state.is_alive:
            continue
        if (target_state.position.x, target_state.position.y) not in occupied_cells:
            continue
        target = spell_target_context(state, actor, target_ref)
        if target is not None:
            targets.append(target)
    return targets
