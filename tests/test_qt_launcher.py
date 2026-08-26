from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from srd_arena.application.scenarios import ScenarioSummary
from srd_arena.application.startup import GameStartup, RunningGame
from srd_arena.frontends.qt import launcher


def test_scenario_picker_delegates_game_creation_to_application_startup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    scenario = ScenarioSummary(
        id="example",
        label="Example Encounter",
        directory=tmp_path,
    )
    running_game = cast(RunningGame, object())

    class StartupStub:
        def __init__(self) -> None:
            self.started: list[Path] = []

        def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
            return (scenario,)

        def start_scenario(self, directory: str | Path) -> RunningGame:
            self.started.append(Path(directory))
            return running_game

    created_windows: list[GameWindowStub] = []

    class GameWindowStub:
        def __init__(self, received: RunningGame) -> None:
            self.received = received
            self.was_shown = False
            created_windows.append(self)

        def show(self) -> None:
            self.was_shown = True

    startup = StartupStub()
    monkeypatch.setattr(launcher, "GameWindow", GameWindowStub)
    picker = launcher.ScenarioPickerWindow(cast(GameStartup, startup))

    buttons = picker.findChildren(QPushButton)
    assert [button.text() for button in buttons] == ["Example Encounter"]

    picker._open_scenario(scenario)

    assert startup.started == [tmp_path]
    assert len(created_windows) == 1
    assert created_windows[0].received is running_game
    assert created_windows[0].was_shown is True
    picker.deleteLater()
    app.processEvents()
