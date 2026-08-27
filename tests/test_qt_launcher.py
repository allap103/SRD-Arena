from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from srd_arena.application.scenarios import ScenarioPresentation, ScenarioSummary
from srd_arena.application.game import RunningGame
from srd_arena.application.startup import GameStartup
import srd_arena.frontends.gui.launcher as launcher


def test_scenario_picker_delegates_game_creation_to_application_startup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    scenario = ScenarioSummary(
        id="example",
        label="Example Encounter",
        presentation=ScenarioPresentation(grid_color="#123456"),
    )
    running_game = cast(RunningGame, object())

    class StartupStub:
        def __init__(self) -> None:
            self.started: list[str] = []

        def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
            return (scenario,)

        def start_scenario(
            self,
            scenario_id: str,
            *,
            automatic_action_limit: int | None = None,
        ) -> RunningGame:
            self.started.append(scenario_id)
            assert automatic_action_limit == 1
            return running_game

    created_presenters: list[GamePresenterStub] = []

    class GamePresenterStub:
        def __init__(self, received: RunningGame) -> None:
            self.received = received
            created_presenters.append(self)

    created_windows: list[GameWindowStub] = []

    class GameWindowStub:
        def __init__(
            self,
            received: GamePresenterStub,
            *,
            image_root: Path | None = None,
            presentation_config: ScenarioPresentation | None = None,
        ) -> None:
            self.received = received
            self.image_root = image_root
            self.presentation_config = presentation_config
            self.was_shown = False
            created_windows.append(self)

        def show(self) -> None:
            self.was_shown = True

    startup = StartupStub()
    monkeypatch.setattr(launcher, "GamePresenter", GamePresenterStub)
    monkeypatch.setattr(launcher, "GameWindow", GameWindowStub)
    image_root = tmp_path / "images"
    picker = launcher.ScenarioPickerWindow(
        cast(GameStartup, startup),
        image_root=image_root,
    )

    buttons = picker.findChildren(QPushButton)
    assert [button.text() for button in buttons] == ["Example Encounter"]

    picker._open_scenario(scenario)

    assert startup.started == ["example"]
    assert len(created_presenters) == 1
    assert created_presenters[0].received is running_game
    assert len(created_windows) == 1
    assert created_windows[0].received is created_presenters[0]
    assert created_windows[0].image_root == image_root
    assert created_windows[0].presentation_config == scenario.presentation
    assert created_windows[0].was_shown is True
    picker.deleteLater()
    app.processEvents()
