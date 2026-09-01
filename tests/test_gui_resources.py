from types import SimpleNamespace
from typing import cast

from srd_arena.engine.api import EncounterObservation
from srd_arena.frontends.gui.presentation.resources import (
    _build_initiative_track,
)


def test_initiative_track_excludes_defeated_creatures() -> None:
    creatures = {
        "fighter": SimpleNamespace(name="Fighter", is_alive=True),
        "droop": SimpleNamespace(name="Droop", is_alive=False),
        "redeye": SimpleNamespace(name="Redeye", is_alive=True),
    }
    encounter = SimpleNamespace(
        decision=SimpleNamespace(creature_ref="fighter"),
        initiative=(
            SimpleNamespace(creature_ref="fighter", total=18),
            SimpleNamespace(creature_ref="droop", total=15),
            SimpleNamespace(creature_ref="redeye", total=12),
        ),
        creature=creatures.__getitem__,
    )

    entries = _build_initiative_track(cast(EncounterObservation, encounter))

    assert [entry.creature_ref for entry in entries] == [
        "fighter",
        "redeye",
    ]
    assert entries[0].is_active
