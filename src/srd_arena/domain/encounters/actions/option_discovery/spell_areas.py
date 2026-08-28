"""Construct spell areas and resolve the creatures whose footprints intersect them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature
from ....geometry import (
    AreaOfEffect,
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    vector_between_positions,
)
from ....spells.definitions import Spell
from ....spells.resolution import SpellTargetContext
from ....spells.rules import spell_area_shape

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_area_targets(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> tuple[SpellTargetContext, ...]:
    """Return legal creature targets intersected by an aimed spell area.

    A direct spell with no constructed area falls back to its selected target.

    >>> from types import SimpleNamespace
    >>> target = SimpleNamespace(target_ref="goblin")
    >>> state = SimpleNamespace(
    ...     _spell_area=lambda *args, **kwargs: None,
    ...     _spell_target_context=lambda actor, ref: target,
    ... )
    >>> spell = Spell("bolt", "Bolt", None, 0)
    >>> spell_area_targets(state, SimpleNamespace(), spell, target_ref="goblin")
    (namespace(target_ref='goblin'),)
    """

    area = self._spell_area(actor, spell, target_ref=target_ref, aim_point=aim_point)
    if area is None:
        if target_ref is None:
            return ()
        target = self._spell_target_context(actor, target_ref)
        return (target,) if target is not None else ()
    return tuple(self._targets_in_area(actor, area))


def spell_area(
    self: EncounterState,
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
    ...     _creature_position=lambda ref: Position(0, 0),
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

    creature_ref = self.current_decision().creature_ref
    creature_position = self._creature_position(creature_ref)
    if spell.geometry_mode == "point_area":
        if aim_point is None:
            return None
        radius_feet = spell.area_size_feet
        if radius_feet is None:
            return None
        radius_squares = int(
            self.definition.grid.distance_from_feet(radius_feet, minimum=1)
        )
        origin = Position(int(aim_point[0]), int(aim_point[1]))
        if spell_area_shape(spell) == "cube":
            return build_point_cube_area(origin, radius_squares, self.definition.grid)
        return build_radius_area(origin, radius_squares, self.definition.grid)
    if spell.geometry_mode != "directional_area":
        return None
    if aim_point is not None:
        if (
            abs(aim_point[0] - (creature_position.x + 0.5)) < 1e-9
            and abs(aim_point[1] - (creature_position.y + 0.5)) < 1e-9
        ):
            return None
        direction = Vector2D(
            aim_point[0] - (creature_position.x + 0.5),
            aim_point[1] - (creature_position.y + 0.5),
        )
    else:
        if target_ref is None:
            return None
        target = self._spell_target_context(actor, target_ref)
        if target is None or target_ref == creature_ref:
            return None
        direction = vector_between_positions(
            creature_position,
            self._creature_position(target_ref),
        )
    length = self._spell_range_squares(spell, actor)
    if length is None:
        return None
    coverage_threshold = self.geometry_config.directional_area_cell_coverage_threshold
    return build_directional_area(
        spell.range_data.get("type"),
        creature_position,
        direction,
        length,
        self.definition.grid,
        coverage_threshold=coverage_threshold,
    )


def targets_in_area(
    self: EncounterState,
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
    ...     _spell_target_context=lambda actor, ref: target,
    ... )
    >>> targets_in_area(state, SimpleNamespace(), area)
    [namespace(target_ref='goblin')]
    """

    occupied_cells = {(cell.x, cell.y) for cell in area.cells}
    targets: list[SpellTargetContext] = []
    for target_ref, target_state in self.creatures.items():
        if not target_state.is_alive:
            continue
        if (target_state.position.x, target_state.position.y) not in occupied_cells:
            continue
        target = self._spell_target_context(actor, target_ref)
        if target is not None:
            targets.append(target)
    return targets
