from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from srd_arena.application.game import RunningGame
from srd_arena.frontends.qt.app import GameWindow
from srd_arena.frontends.qt.ui.encounter.panel_renderer import (
    EncounterPanelRenderer,
)
from srd_arena.infrastructure.scenarios import load_scenario


SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_game_window_delegates_encounter_controls_to_panel_renderer() -> None:
    app = QApplication.instance() or QApplication([])
    session = load_scenario(SCENARIOS_ROOT / "slow_showcase").create_session()

    window = GameWindow(RunningGame(session))

    assert isinstance(window._encounter_panel_renderer, EncounterPanelRenderer)
    assert window.health_status_layout.count() == 1
    assert window.movement_status_layout.count() == 1
    assert window.initiative_layout.count() > 1
    assert window.actions_section_layout.count() > 0
    assert window.end_turn_button.text() in {"End Turn", "Pass Reaction"}

    window.close()
    window.deleteLater()
    app.processEvents()
