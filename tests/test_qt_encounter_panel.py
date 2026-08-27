from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame

from srd_arena.application.game import RunningGame
from srd_arena.frontends.gui.app import GameWindow
from srd_arena.frontends.gui.ui.encounter.panel_renderer import (
    EncounterPanelRenderer,
)
from srd_arena.infrastructure.scenarios import load_scenario_directory


SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_game_window_delegates_encounter_controls_to_panel_renderer() -> None:
    app = QApplication.instance() or QApplication([])
    session = load_scenario_directory(SCENARIOS_ROOT / "slow_showcase").create_session()

    window = GameWindow(RunningGame(session), show_encounter_json=True)

    assert isinstance(window._encounter_panel_renderer, EncounterPanelRenderer)
    bindings = window.sidebar.encounter_bindings
    assert bindings.health_layout.count() == 1
    assert bindings.movement_layout.count() == 1
    assert len(window.surface.findChildren(QFrame, "initiativeCard")) > 1
    assert bindings.actions_layout.count() > 0
    assert bindings.end_turn_button.text() in {"End Turn", "Pass Reaction"}

    window.sidebar.show_attributes()
    assert "Name:" in window.sidebar._attributes_text.toPlainText()
    window.sidebar.show_inventory()
    assert window.sidebar._inventory_text.toPlainText()
    window.sidebar.show_json()
    payload = json.loads(window.sidebar._json_text.toPlainText())
    assert payload["encounter_active"] is True
    window.sidebar.show_root()
    assert window.sidebar._stack.currentIndex() == window.sidebar._combat_index

    window.close()
    window.deleteLater()
    app.processEvents()
