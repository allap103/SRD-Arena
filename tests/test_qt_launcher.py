from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

import srd_arena.frontends.gui.launcher as launcher
from srd_arena.application.game import RunningGame
from srd_arena.application.scenarios import ScenarioPresentation, ScenarioSummary
from srd_arena.application.startup import GameStartup
from srd_arena.frontends.gui import app as game_app


def test_scenario_picker_delegates_game_creation_to_application_startup(
    monkeypatch: pytest.MonkeyPatch,
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
            pace_automatic_actions: bool = False,
        ) -> RunningGame:
            self.started.append(scenario_id)
            assert pace_automatic_actions is False
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
            pace_automatic_actions: bool = True,
        ) -> None:
            self.received = received
            self.image_root = image_root
            self.presentation_config = presentation_config
            self.pace_automatic_actions = pace_automatic_actions
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
        pace_automatic_actions=False,
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
    assert created_windows[0].pace_automatic_actions is False
    assert created_windows[0].was_shown is True
    picker.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(
    ("pace_automatic_actions", "expected_delay_ms"),
    [(True, game_app.AUTOMATIC_ACTION_DELAY_MS), (False, 0)],
)
def test_automatic_action_pacing_selects_the_gui_timer_delay(
    monkeypatch: pytest.MonkeyPatch,
    pace_automatic_actions: bool,
    expected_delay_ms: int,
) -> None:
    scheduled_delays: list[int] = []
    monkeypatch.setattr(
        game_app.QTimer,
        "singleShot",
        lambda delay_ms, _callback: scheduled_delays.append(delay_ms),
    )
    window = cast(
        game_app.GameWindow,
        SimpleNamespace(
            _automatic_step_scheduled=False,
            _pace_automatic_actions=pace_automatic_actions,
            _advance_automatic_step=lambda: None,
            presenter=SimpleNamespace(
                observation=SimpleNamespace(
                    encounter=object(),
                    transition=None,
                    requires_automatic_advance=True,
                )
            ),
        ),
    )

    game_app.GameWindow._schedule_ai_step_if_needed(window)

    assert scheduled_delays == [expected_delay_ms]
    assert window._automatic_step_scheduled is True
