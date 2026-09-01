from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

import srd_arena.frontends.gui.launcher as launcher
from srd_arena.content.encounters import (
    EncounterCatalog,
    EncounterPresentation,
    EncounterSummary,
)
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.engine.session import Session
from srd_arena.frontends.gui import app as game_app


def test_encounter_picker_loads_content_then_creates_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    encounter = EncounterSummary(
        id="example",
        label="Example Encounter",
        presentation=EncounterPresentation(grid_color="#123456"),
    )
    encounters = (
        EncounterSummary("zulu", "Zulu Demo"),
        encounter,
        EncounterSummary("alpha", "alpha Demo"),
    )
    session = cast(Session, object())

    class CatalogStub:
        def __init__(self) -> None:
            self.loaded: list[str] = []

        def available_encounters(self) -> tuple[EncounterSummary, ...]:
            return encounters

        def load_encounter(self, encounter_id: str) -> EncounterDefinition:
            self.loaded.append(encounter_id)
            return cast(EncounterDefinition, object())

    created_presenters: list[GamePresenterStub] = []

    class GamePresenterStub:
        def __init__(self, received: Session) -> None:
            self.received = received
            created_presenters.append(self)

    created_windows: list[GameWindowStub] = []

    class GameWindowStub:
        def __init__(
            self,
            received: GamePresenterStub,
            *,
            image_root: Path | None = None,
            presentation_config: EncounterPresentation | None = None,
            pause_between_automatic_actions: bool = True,
        ) -> None:
            self.received = received
            self.image_root = image_root
            self.presentation_config = presentation_config
            self.pause_between_automatic_actions = pause_between_automatic_actions
            self.was_shown = False
            created_windows.append(self)

        def show(self) -> None:
            self.was_shown = True

    catalog = CatalogStub()

    def create_session(_encounter: EncounterDefinition) -> Session:
        return session

    monkeypatch.setattr(launcher, "GamePresenter", GamePresenterStub)
    monkeypatch.setattr(launcher, "GameWindow", GameWindowStub)
    image_root = tmp_path / "images"
    picker = launcher.EncounterPickerWindow(
        cast(EncounterCatalog, catalog),
        image_root=image_root,
        pause_between_automatic_actions=False,
        session_factory=create_session,
    )

    buttons = picker.findChildren(QPushButton)
    assert [button.text() for button in buttons] == [
        "alpha Demo",
        "Example Encounter",
        "Zulu Demo",
    ]
    assert "Start a new session from any available encounter." not in {
        label.text() for label in picker.findChildren(QLabel)
    }

    picker._open_encounter(encounter)

    assert catalog.loaded == ["example"]
    assert len(created_presenters) == 1
    assert created_presenters[0].received is session
    assert len(created_windows) == 1
    assert created_windows[0].received is created_presenters[0]
    assert created_windows[0].image_root == image_root
    assert created_windows[0].presentation_config == encounter.presentation
    assert created_windows[0].pause_between_automatic_actions is False
    assert created_windows[0].was_shown is True
    picker.deleteLater()
    app.processEvents()


def test_encounter_picker_displays_content_loading_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    encounter = EncounterSummary("invalid", "Invalid Encounter")
    catalog = Mock(spec=EncounterCatalog)
    catalog.available_encounters.return_value = (encounter,)
    catalog.load_encounter.side_effect = ValueError(
        "Starting position lies outside the grid."
    )
    displayed_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message: displayed_errors.append((title, message)),
    )
    picker = launcher.EncounterPickerWindow(catalog)

    picker._open_encounter(encounter)

    assert displayed_errors == [
        ("Unable to load encounter", "Starting position lies outside the grid.")
    ]
    assert picker._game_window is None
    picker.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(
    ("pause_between_automatic_actions", "expected_delay_ms"),
    [(True, game_app.AUTOMATIC_ACTION_DELAY_MS), (False, 0)],
)
def test_automatic_action_pacing_selects_the_gui_timer_delay(
    monkeypatch: pytest.MonkeyPatch,
    pause_between_automatic_actions: bool,
    expected_delay_ms: int,
) -> None:
    scheduled_delays: list[int] = []
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        lambda delay_ms, _callback: scheduled_delays.append(delay_ms),
    )
    window = cast(
        game_app.GameWindow,
        SimpleNamespace(
            _automatic_step_scheduled=False,
            _pause_between_automatic_actions=pause_between_automatic_actions,
            _advance_automatic_step=lambda: None,
            presenter=SimpleNamespace(
                observation=SimpleNamespace(
                    encounter=object(),
                    completion=None,
                    requires_automatic_advance=True,
                )
            ),
        ),
    )

    game_app.GameWindow._schedule_ai_step_if_needed(window)

    assert scheduled_delays == [expected_delay_ms]
    assert window._automatic_step_scheduled is True


@pytest.mark.parametrize("pause_between_automatic_actions", [True, False])
def test_gui_selects_automatic_advance_granularity(
    pause_between_automatic_actions: bool,
) -> None:
    observation = SimpleNamespace(
        encounter=object(),
        requires_automatic_advance=True,
    )
    update = Mock()
    presenter = Mock(observation=observation)
    presenter.refresh.return_value = observation
    presenter.advance_one_automatic_action.return_value = update
    presenter.advance_until_input_required.return_value = update
    apply_turn_result = Mock()
    window = cast(
        game_app.GameWindow,
        SimpleNamespace(
            _automatic_step_scheduled=True,
            _pause_between_automatic_actions=pause_between_automatic_actions,
            presenter=presenter,
            _apply_turn_result=apply_turn_result,
        ),
    )

    game_app.GameWindow._advance_automatic_step(window)

    assert window._automatic_step_scheduled is False
    if pause_between_automatic_actions:
        presenter.advance_one_automatic_action.assert_called_once_with()
        presenter.advance_until_input_required.assert_not_called()
    else:
        presenter.advance_one_automatic_action.assert_not_called()
        presenter.advance_until_input_required.assert_called_once_with()
    apply_turn_result.assert_called_once_with(update)
