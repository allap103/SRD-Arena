from pathlib import Path

import pytest

from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.application.observations import observe_session
from srd_arena.frontends.gui.ui.encounter.area_previews import (
    area_overlay_label,
    overlay_cells,
    overlay_origin,
    preview_area_overlay,
)
from srd_arena.frontends.gui.ui.encounter.targeting import (
    mode_for_action,
    pending_area_overlay,
)
from srd_arena.frontends.shared.models import BattlefieldView
from srd_arena.infrastructure.scenarios import load_scenario_directory


SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_area_overlay_readers_ignore_malformed_geometry() -> None:
    area: dict[str, object] = {
        "shape": "line",
        "origin": {"x": 2, "y": 3},
        "cells": [
            {"x": 2, "y": 3},
            {"x": "invalid", "y": 4},
            None,
        ],
    }

    assert overlay_cells(area) == {(2, 3)}
    assert overlay_origin(area) == (2, 3)
    assert area_overlay_label(area) == "Line AoE"
    assert overlay_cells({"cells": "invalid"}) == set()
    assert overlay_origin({"origin": {"x": 2}}) is None


def test_slow_pending_area_preview_is_an_eight_square_cube(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _tempo_archmage_first(self: EncounterState) -> None:
        self.initiative_entries = []
        self.initiative_order = [
            "tempo_archmage",
            *(ref for ref in self.creatures if ref != "tempo_archmage"),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _tempo_archmage_first)
    session = load_scenario_directory(SCENARIOS_ROOT / "slow_showcase").create_session()
    session.read()
    observation = observe_session(session)
    slow_action = next(
        action
        for action in observation.scene.action_details
        if action.label == "Cast Slow"
    )

    mode = mode_for_action(slow_action)
    overlay = pending_area_overlay(observation.scene.action_details, mode)

    assert overlay is not None
    assert overlay["shape"] == "cube"

    preview = preview_area_overlay(
        overlay,
        (10.5, 6.5),
        BattlefieldView(
            width=22,
            height=14,
            creatures=[],
            summary_text="",
        ),
    )

    assert preview is not None
    assert preview["shape"] == "cube"
    assert preview["origin"] == {"x": 10, "y": 6}
    cells = preview["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 64
    assert {(cell["x"], cell["y"]) for cell in cells if isinstance(cell, dict)} == {
        (x, y) for y in range(3, 11) for x in range(7, 15)
    }
