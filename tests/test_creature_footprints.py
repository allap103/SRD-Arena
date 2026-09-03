import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from srd_arena.content.encounters import load_encounter_directory, load_encounter_file
from srd_arena.domain.creatures import Attributes, Creature, Equipment, Inventory
from srd_arena.domain.encounters.actions.eligibility_rules.common import MovementRule
from srd_arena.domain.encounters.actions.option_discovery.spell_areas import (
    targets_in_area,
)
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.spatial import (
    creature_distance,
    creature_occupied_cells,
    placement_is_free,
    validate_creature_placements,
)
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.geometry import AreaOfEffect, Grid, MovementBudget, Position
from srd_arena.engine.session import Session

ROOT = Path(__file__).resolve().parents[1]


def _creature_state(
    position: Position,
    size: str,
    *,
    alive: bool = True,
) -> EncounterCreatureState:
    creature = Creature(
        size.casefold(),
        size,
        "",
        Inventory(),
        Attributes(20 if alive else 0, 1, 10, 10, 10, 10, 10, 10, 10),
        Equipment(),
        size=size,
    )
    return EncounterCreatureState(
        creature_id=creature.id,
        position=position,
        creature=creature,
        behavior=EncounterBehavior("wait"),
        movement_remaining=MovementBudget(6),
    )


def _state(*creatures: tuple[str, EncounterCreatureState]) -> EncounterState:
    return EncounterState(
        encounter_id="footprints",
        definition=EncounterDefinition("footprints", Grid(10, 10)),
        creatures=dict(creatures),
    )


def test_large_creature_occupies_a_two_by_two_footprint() -> None:
    state = _state(("ogre", _creature_state(Position(2, 3), "L")))

    assert creature_occupied_cells(state, "ogre") == (
        Position(2, 3),
        Position(3, 3),
        Position(2, 4),
        Position(3, 4),
    )


def test_distance_uses_nearest_occupied_cells() -> None:
    state = _state(
        ("ogre", _creature_state(Position(1, 1), "L")),
        ("hero", _creature_state(Position(4, 2), "M")),
    )

    assert creature_distance(state, "ogre", "hero") == 2


def test_ranged_attack_proximity_uses_nearest_occupied_cells() -> None:
    state = _state(
        ("ogre", _creature_state(Position(0, 0), "L")),
        ("hero", _creature_state(Position(2, 1), "M")),
    )
    mode = attack_roll_mode_for(
        state,
        "ogre",
        "hero",
        "ranged",
        Position(0, 0),
        (Position(2, 1),),
        nearby_opponent_refs=("hero",),
    )

    assert mode == "disadvantage"


def test_placement_checks_the_complete_destination_footprint() -> None:
    state = _state(
        ("ogre", _creature_state(Position(0, 0), "L")),
        ("blocker", _creature_state(Position(2, 1), "M")),
    )

    assert (
        placement_is_free(
            state,
            "ogre",
            Position(1, 0),
            ignored_refs={"ogre"},
        )
        is False
    )
    assert (
        placement_is_free(
            state,
            "ogre",
            Position(8, 8),
            ignored_refs={"ogre"},
        )
        is True
    )
    assert (
        placement_is_free(
            state,
            "ogre",
            Position(9, 9),
            ignored_refs={"ogre"},
        )
        is False
    )


def test_movement_rule_rejects_a_blocked_large_destination_footprint() -> None:
    state = _state(
        ("ogre", _creature_state(Position(0, 0), "L")),
        ("blocker", _creature_state(Position(2, 1), "M")),
    )
    action = EncounterAction("Move right", "move", "right")

    failure = MovementRule().check(state, "ogre", action)

    assert failure is not None
    assert failure.code == "destination_blocked"


def test_area_affects_a_large_creature_when_any_occupied_cell_is_covered() -> None:
    ogre = _creature_state(Position(2, 2), "L")
    state = _state(("ogre", ogre))
    target = SimpleNamespace(target_ref="ogre")
    area = AreaOfEffect("cube", Position(3, 3), (Position(3, 3),))

    with patch(
        "srd_arena.domain.encounters.actions.option_discovery.spell_areas."
        "spell_target_context",
        return_value=target,
    ):
        resolved = targets_in_area(state, ogre.creature, area)

    assert resolved == [target]


def test_initial_placement_rejects_overlapping_footprints() -> None:
    state = _state(
        ("ogre", _creature_state(Position(1, 1), "L")),
        ("hero", _creature_state(Position(2, 2), "M")),
    )

    with pytest.raises(ValueError, match="overlap at \\(2, 2\\)"):
        validate_creature_placements(state)


def test_content_loading_rejects_overlapping_large_footprints(
    tmp_path: Path,
) -> None:
    encounter_path = tmp_path / "overlap.json"
    encounter_path.write_text(
        json.dumps(
            {
                "id": "overlap",
                "grid": {"width": 4, "height": 4},
                "teams": [
                    {"id": "one", "name": "One", "controller": "external"},
                    {"id": "two", "name": "Two", "controller": "external"},
                ],
                "creatures": [
                        {
                            "id": "ogre",
                            "name": "Ogre",
                        "metadata": {"size": "L"},
                        "start": {"x": 0, "y": 0},
                        "team_id": "one",
                    },
                        {
                            "id": "hero",
                            "name": "Hero",
                        "start": {"x": 1, "y": 1},
                        "team_id": "two",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="overlap at \\(1, 1\\)"):
        load_encounter_file(encounter_path)


def test_archived_large_creatures_expose_all_occupied_cells() -> None:
    encounter = load_encounter_directory(
        ROOT / "content" / "encounters" / "archive" / "multiattack_showcase"
    )
    observation = Session(encounter, seed=42).observe()
    assert observation.encounter is not None

    frostwing = observation.encounter.creature("player")

    assert frostwing.size == "H"
    assert len(frostwing.occupied_cells) == 9
