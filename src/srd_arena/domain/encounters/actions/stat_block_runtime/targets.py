"""Resolve targets for authored stat-block saving-throw actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures.stat_block_actions import SavingThrowActionDefinition
from srd_arena.domain.geometry import (
    Vector2D,
    build_directional_area,
    vector_between_positions,
)

from ...rule_queries.obstructions import cells_with_line_of_effect
from ...spatial import creature_intersects_cells

if TYPE_CHECKING:
    from ...encounter import EncounterState


def stat_block_target_refs(
    state: EncounterState,
    creature_ref: str,
    aim: str | tuple[float, float],
    definition: SavingThrowActionDefinition,
) -> tuple[str, ...]:
    """Resolve creature references covered by a stat-block action target.

    Direct targets require no geometry; area definitions continue through the
    same function and return every living creature whose cell is covered.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.capabilities import CapabilityTarget, OutcomeStage
    >>> self_definition = SavingThrowActionDefinition(
    ...     "Pulse", CapabilityTarget("self"), "con", 12,
    ...     (OutcomeStage(()),), (), "none", (),
    ... )
    >>> stat_block_target_refs(
    ...     SimpleNamespace(), "caster", "ignored", self_definition
    ... )
    ('caster',)
    >>> target_definition = SavingThrowActionDefinition(
    ...     "Glare", CapabilityTarget("creature"), "wis", 12,
    ...     (OutcomeStage(()),), (), "none", (),
    ... )
    >>> stat_block_target_refs(
    ...     SimpleNamespace(), "caster", "target", target_definition
    ... )
    ('target',)
    """
    target = definition.target
    if target.kind == "self":
        return (creature_ref,)
    if target.kind == "creature":
        if not isinstance(aim, str):
            raise ValueError("A creature-targeted action requires a creature target.")
        return (aim,)
    if target.origin != "self":
        raise NotImplementedError("Point-origin stat-block areas are not executable.")
    actor_position = state.creatures[creature_ref].position
    direction = (
        vector_between_positions(actor_position, state.creatures[aim].position)
        if isinstance(aim, str)
        else Vector2D(
            aim[0] - (actor_position.x + 0.5),
            aim[1] - (actor_position.y + 0.5),
        )
    )
    grid = state.definition.grid
    size_squares = int(
        grid.distance_from_feet(target.size_feet or grid.square_size_feet, minimum=1)
    )
    width_squares = max(
        1.0,
        (target.width_feet or grid.square_size_feet) / grid.square_size_feet,
    )
    area = build_directional_area(
        target.shape,
        actor_position,
        direction,
        size_squares,
        state.definition.grid,
        width_squares=width_squares,
        coverage_threshold=(
            state.geometry_config.directional_area_cell_coverage_threshold
        ),
    )
    if area is None:
        raise NotImplementedError(f"Area shape '{target.shape}' is not executable.")
    visible_cells = cells_with_line_of_effect(state, area.origin, area.cells)
    occupied = {(cell.x, cell.y) for cell in visible_cells}
    return tuple(
        target_ref
        for target_ref, target_state in state.creatures.items()
        if target_state.is_alive
        and creature_intersects_cells(state, target_ref, occupied)
    )
