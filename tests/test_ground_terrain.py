import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from srd_arena.content.encounters import load_encounter_file
from srd_arena.domain.capabilities import (
    AutomaticResolution,
    CapabilityDefinition,
    CapabilityTarget,
    Outcome,
)
from srd_arena.domain.creatures import Attributes, Creature, Equipment, Inventory
from srd_arena.domain.encounters import (
    CoverDegree,
    EncounterBehavior,
    EncounterDefinition,
    TerrainCell,
    TerrainMovementMode,
    TerrainTraversal,
)
from srd_arena.domain.encounters.actions.creature_actions.movement_candidates import (
    movement_action_candidates,
)
from srd_arena.domain.encounters.actions.eligibility_rules.common import MovementRule
from srd_arena.domain.encounters.actions.option_discovery.spell_areas import spell_area
from srd_arena.domain.encounters.actions.spell_runtime.context import (
    build_spell_action_context,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.rule_queries.obstructions import (
    cell_has_line_of_effect,
    cells_with_line_of_effect,
    cover_between,
)
from srd_arena.domain.encounters.spatial import placement_is_free
from srd_arena.domain.geometry import Grid, MovementBudget, Position
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.resolution import SpellTargetContext
from srd_arena.domain.spells.rules import spell_action_payload


def _creature_state(position: Position, *, size: str = "M") -> EncounterCreatureState:
    creature = Creature(
        "creature",
        "Creature",
        "",
        Inventory(),
        Attributes(20, 1, 10, 10, 10, 10, 10, 10, 10),
        Equipment(),
        size=size,
    )
    return EncounterCreatureState(
        creature.id,
        creature,
        position,
        EncounterBehavior("wait"),
        movement_remaining=MovementBudget(6),
    )


def _state(*terrain: TerrainCell, size: str = "M") -> EncounterState:
    definition = EncounterDefinition(
        "terrain",
        Grid(8, 8),
        terrain=terrain,
    )
    return EncounterState(
        "terrain",
        definition,
        {"actor": _creature_state(Position(1, 1), size=size)},
    )


def test_encounter_loader_builds_typed_terrain(tmp_path: Path) -> None:
    path = tmp_path / "encounter.json"
    path.write_text(
        json.dumps(
            {
                "id": "terrain",
                "grid": {"width": 5, "height": 5},
                "teams": [
                    {
                        "id": "team",
                        "name": "Team",
                        "controller": "external",
                    }
                ],
                "creatures": [
                    {
                        "id": "hero",
                        "name": "Hero",
                        "team_id": "team",
                        "start": {"x": 0, "y": 0},
                    }
                ],
                "terrain": [
                    {
                        "position": {"x": 2, "y": 2},
                        "traversal": "blocked",
                        "cover": "total",
                        "movement_mode": "climb",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    terrain = load_encounter_file(path).definition.terrain

    assert terrain == (
        TerrainCell(
            Position(2, 2),
            TerrainTraversal.BLOCKED,
            CoverDegree.TOTAL,
            TerrainMovementMode.CLIMB,
        ),
    )


def test_encounter_schema_rejects_duplicate_terrain_cells(tmp_path: Path) -> None:
    path = tmp_path / "encounter.json"
    path.write_text(
        json.dumps(
            {
                "id": "terrain",
                "grid": {"width": 5, "height": 5},
                "terrain": [
                    {"position": {"x": 2, "y": 2}},
                    {"position": {"x": 2, "y": 2}},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="terrain positions must be unique"):
        load_encounter_file(path)


def test_encounter_loader_rejects_creature_on_blocked_terrain(tmp_path: Path) -> None:
    path = tmp_path / "encounter.json"
    path.write_text(
        json.dumps(
            {
                "id": "terrain",
                "grid": {"width": 5, "height": 5},
                "teams": [
                    {
                        "id": "team",
                        "name": "Team",
                        "controller": "external",
                    }
                ],
                "creatures": [
                    {
                        "id": "hero",
                        "name": "Hero",
                        "team_id": "team",
                        "start": {"x": 1, "y": 1},
                    }
                ],
                "terrain": [
                    {
                        "position": {"x": 1, "y": 1},
                        "traversal": "blocked",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="overlaps blocked terrain"):
        load_encounter_file(path)


def test_blocked_terrain_rejects_any_overlapping_footprint() -> None:
    state = _state(
        TerrainCell(Position(3, 2), TerrainTraversal.BLOCKED),
        size="L",
    )

    assert not placement_is_free(state, "actor", Position(2, 1))


def test_movement_options_expose_destination_specific_difficult_cost() -> None:
    state = _state(TerrainCell(Position(2, 1), TerrainTraversal.DIFFICULT))

    actions = movement_action_candidates(state, "actor")
    costs = {action.value: int(action.cost.movement) for action in actions}

    assert costs["right"] == 2
    assert costs["left"] == 1


def test_diagonal_movement_cannot_clip_a_blocked_terrain_corner() -> None:
    state = _state(TerrainCell(Position(2, 1), TerrainTraversal.BLOCKED))
    action = EncounterAction("Move down-right", "move", "down-right")

    failure = MovementRule().check(state, "actor", action)

    assert failure is not None
    assert failure.code == "destination_blocked"


def test_cover_uses_the_most_protective_intervening_terrain() -> None:
    definition = EncounterDefinition(
        "cover",
        Grid(8, 8),
        terrain=(
            TerrainCell(Position(1, 0), cover=CoverDegree.HALF),
            TerrainCell(Position(2, 0), cover=CoverDegree.THREE_QUARTERS),
        ),
    )
    state = EncounterState(
        "cover",
        definition,
        {
            "source": _creature_state(Position(0, 0)),
            "target": _creature_state(Position(4, 0)),
        },
    )

    result = cover_between(state, "source", "target")

    assert result.degree is CoverDegree.THREE_QUARTERS
    assert result.bonus == 5
    assert result.terrain_cells == (Position(2, 0),)


def test_intervening_creature_provides_half_cover() -> None:
    state = EncounterState(
        "cover",
        EncounterDefinition("cover", Grid(8, 8)),
        {
            "source": _creature_state(Position(0, 0)),
            "blocker": _creature_state(Position(2, 0)),
            "target": _creature_state(Position(4, 0)),
        },
    )

    result = cover_between(state, "source", "target")

    assert result.degree is CoverDegree.HALF
    assert result.creature_refs == ("blocker",)


def test_total_cover_blocks_cells_and_every_cell_behind_them() -> None:
    state = _state(
        TerrainCell(
            Position(2, 1),
            TerrainTraversal.BLOCKED,
            CoverDegree.TOTAL,
        )
    )
    targets = (Position(2, 1), Position(3, 1), Position(1, 2))

    assert not cell_has_line_of_effect(state, Position(1, 1), Position(3, 1))
    assert cells_with_line_of_effect(state, Position(1, 1), targets) == (
        Position(1, 2),
    )


def test_large_target_uses_its_least_obstructed_footprint_ray() -> None:
    definition = EncounterDefinition(
        "cover",
        Grid(8, 8),
        terrain=(TerrainCell(Position(3, 1), cover=CoverDegree.TOTAL),),
    )
    state = EncounterState(
        "cover",
        definition,
        {
            "source": _creature_state(Position(0, 1)),
            "target": _creature_state(Position(4, 1), size="L"),
        },
    )

    assert cover_between(state, "source", "target").degree is CoverDegree.NONE


def test_spell_context_applies_partial_cover_to_ac_and_dexterity_saves() -> None:
    definition = EncounterDefinition(
        "cover",
        Grid(8, 8),
        terrain=(TerrainCell(Position(2, 0), cover=CoverDegree.HALF),),
    )
    source = _creature_state(Position(0, 0))
    target = _creature_state(Position(4, 0))
    state = EncounterState(
        "cover",
        definition,
        {"source": source, "target": target},
    )
    spell = Spell(
        "test_spell",
        "Test Spell",
        None,
        1,
        definition=CapabilityDefinition(
            CapabilityTarget("creature"),
            AutomaticResolution(Outcome()),
        ),
    )
    target_context = SpellTargetContext(target.creature, "target", "Target")

    context = build_spell_action_context(
        state,
        actor=source.creature,
        spell=spell,
        payload=spell_action_payload("test_spell"),
        creature_ref="source",
        target=target_context,
        targets=(target_context,),
        area=None,
        cast_level=1,
    )

    assert context.target_armor_classes["target"] == 12
    assert context.saving_throw_cover_bonuses["target"] == 2


def test_point_area_does_not_extend_through_total_cover() -> None:
    definition = EncounterDefinition(
        "cover",
        Grid(8, 8),
        terrain=(TerrainCell(Position(2, 1), cover=CoverDegree.TOTAL),),
    )
    source = _creature_state(Position(0, 0))
    state = EncounterState(
        "cover",
        definition,
        {"source": source},
        initiative_order=["source"],
    )
    spell = Spell(
        "burst",
        "Burst",
        None,
        1,
        geometry_mode="point_area",
        area_size_feet=15,
    )

    area = spell_area(state, source.creature, spell, aim_point=(1.0, 1.0))

    assert area is not None
    assert Position(1, 2) in area.cells
    assert Position(2, 1) not in area.cells
    assert Position(3, 1) not in area.cells
