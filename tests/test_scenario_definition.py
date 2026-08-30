from __future__ import annotations

import pytest

from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.geometry import Grid
from srd_arena.domain.scenarios import ScenarioDefinition


def test_scenario_definition_owns_ordered_encounters() -> None:
    first = EncounterDefinition("first", Grid(2, 2))
    second = EncounterDefinition("second", Grid(3, 3))

    scenario = ScenarioDefinition(
        id="demo",
        display_name="Demo",
        encounters={"first": first, "second": second},
        encounter_order=("first", "second"),
        start_encounter_id="first",
    )

    assert scenario.get_encounter("first") is first
    assert scenario.encounter_order == ("first", "second")
    assert scenario.start_encounter_id == "first"


def test_scenario_definition_rejects_missing_ordered_encounter() -> None:
    encounter = EncounterDefinition("first", Grid(2, 2))

    with pytest.raises(ValueError, match="missing encounters: second"):
        ScenarioDefinition(
            id="demo",
            display_name="Demo",
            encounters={"first": encounter},
            encounter_order=("first", "second"),
            start_encounter_id="first",
        )
