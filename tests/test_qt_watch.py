"""Spectator controls own playback; ordinary GUI controls cannot mutate combat."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import torch
from PySide6.QtWidgets import QApplication

from srd_arena.frontends.gui.watch import WatchWindow
from srd_arena.training.checkpoint import LoadedCheckpoint
from srd_arena.training.config import load_training_config
from srd_arena.training.model import CandidatePolicy
from srd_arena.training.playback import ModelPlayback


def test_watch_pause_step_restart_and_close() -> None:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication([])
    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(update={"max_decisions": 1})
    driver = ModelPlayback(
        LoadedCheckpoint(config, CandidatePolicy().eval(), torch.device("cpu"))
    )
    window = WatchWindow(driver, paused=True)
    try:
        window.show()
        app.processEvents()
        assert not window.timer.isActive()
        assert not window._automatic_step_scheduled
        before = driver.observe()
        window._select_action(before.scene.action_details[0].id)
        window._end_turn()
        window._handle_battlefield_point_clicked(3.0, 3.0)
        assert driver.observe() == before
        window.play_button.click()
        assert window.timer.isActive()
        window.play_button.click()
        assert not window.timer.isActive()
        window.delay_control.setValue(250)
        assert window.timer.interval() == 250
        window.sidebar.pop_out_combat_log()
        log_window = window.sidebar._log_window
        assert log_window is not None and log_window.isVisible()
        window.step_button.click()
        assert driver.finished
        assert "decision_limit" in window.playback_status.text()
        assert not window.timer.isActive()
        assert not window.play_button.isEnabled()
        window.restart_button.click()
        assert not driver.finished
        assert log_window.isVisible()
        assert window.sidebar._log_body.parentWidget() is log_window
        assert window.play_button.isEnabled()
        assert not window.timer.isActive()
        window.set_playing(True)
        window.close()
        assert not window.timer.isActive()
        assert not log_window.isVisible()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_watch_stops_on_controller_error() -> None:
    from srd_arena.content.encounters import EncounterCatalog
    from srd_arena.engine.api import GameObservation, GameUpdate, Session

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication([])

    class Driver:
        status = "Ready"
        finished = False

        def __init__(self) -> None:
            self.session = Session(
                EncounterCatalog().load_encounter("warlock_training"), seed=42
            )

        def observe(self) -> GameObservation:
            return self.session.observe()

        def advance(self) -> GameUpdate | None:
            raise RuntimeError("test inference failure")

        def reset(self) -> None:
            self.session.reset(seed=42)

    window = WatchWindow(Driver(), paused=True)
    try:
        window.step_once()
        assert "test inference failure" in window.playback_status.text()
        assert not window.timer.isActive()
        assert not window.step_button.isEnabled()
        window.restart()
        assert window.step_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
