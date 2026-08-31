from __future__ import annotations

from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.geometry import Grid


def test_encounter_definition_is_the_complete_playable_unit() -> None:
    encounter = EncounterDefinition(
        id="duel",
        grid=Grid(5, 4),
        display_name="Duel",
    )

    assert encounter.id == "duel"
    assert encounter.display_name == "Duel"
    assert encounter.grid == Grid(5, 4)
    assert not hasattr(encounter, "encounter_order")
    assert not hasattr(encounter, "start_encounter_id")
