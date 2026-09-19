"""Spectator controls for a paced controller, without a learning-library import."""

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QPushButton, QSpinBox, QToolBar

from srd_arena.content.encounters import EncounterPresentation
from srd_arena.engine.api import GameObservation, GameUpdate
from srd_arena.frontends.gui.app import GameWindow
from srd_arena.frontends.gui.presenter import GamePresenter


class PlaybackDriver(Protocol):
    """Supply one paced update and a separate human-readable spectator view."""

    @property
    def status(self) -> str: ...

    @property
    def finished(self) -> bool: ...

    def observe(self) -> GameObservation: ...
    def advance(self) -> GameUpdate | None: ...
    def reset(self) -> None: ...


class WatchWindow(GameWindow):
    """Watch a controller with pause, single-step, restart and pacing controls."""

    def __init__(
        self,
        driver: PlaybackDriver,
        *,
        image_root: Path | None = None,
        presentation_config: EncounterPresentation | None = None,
        delay_ms: int = 500,
        paused: bool = False,
    ) -> None:
        if not 20 <= delay_ms <= 10000:
            raise ValueError("Playback delay must be between 20 and 10000 ms")
        self.driver = driver
        self._playing = False
        self._busy = False
        self._error: str | None = None
        super().__init__(
            GamePresenter(None, observe=driver.observe),
            image_root=image_root,
            presentation_config=presentation_config,
            interactive=False,
            manage_automatic_actions=False,
        )
        self.setWindowTitle("SRD Arena — Watch model")
        self.timer = QTimer(self)
        self.timer.setInterval(delay_ms)
        self.timer.timeout.connect(self._tick)
        toolbar = QToolBar("Playback", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(lambda: self.set_playing(not self._playing))
        toolbar.addWidget(self.play_button)
        self.step_button = QPushButton("Step")
        self.step_button.clicked.connect(self.step_once)
        toolbar.addWidget(self.step_button)
        self.restart_button = QPushButton("Restart")
        self.restart_button.clicked.connect(self.restart)
        toolbar.addWidget(self.restart_button)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Delay: "))
        self.delay_control = QSpinBox()
        self.delay_control.setRange(20, 10000)
        self.delay_control.setSingleStep(100)
        self.delay_control.setSuffix(" ms")
        self.delay_control.setValue(delay_ms)
        self.delay_control.valueChanged.connect(self.timer.setInterval)
        toolbar.addWidget(self.delay_control)
        toolbar.addSeparator()
        self.playback_status = QLabel()
        self.playback_status.setTextFormat(Qt.TextFormat.PlainText)
        toolbar.addWidget(self.playback_status)
        self.set_playing(not paused)

    def set_playing(self, playing: bool) -> None:
        """Start or pause the sole controller timer; completed runs stay stopped."""
        self._playing = playing and not self.driver.finished and self._error is None
        if self._playing:
            self.timer.start()
        else:
            self.timer.stop()
        self._sync_controls()

    def step_once(self) -> None:
        """Pause and resolve one model command or one scripted action."""
        self.set_playing(False)
        self._tick()

    def restart(self) -> None:
        """Restart with saved seeds and remain paused for inspection."""
        self.set_playing(False)
        try:
            self.driver.reset()
            self._error = None
            self._combat_log_scene_id = None
            self._logged_round_number = None
            self.presenter.clear_target_mode()
            self.presenter.refresh()
            self.refresh_view()
        except Exception as exc:
            self._error = f"Playback stopped: {exc}"
        self._sync_controls()

    def _tick(self) -> None:
        if self._busy or self.driver.finished or self._error is not None:
            self.set_playing(False)
            return
        self._busy = True
        try:
            update = self.driver.advance()
            if update is not None:
                self.apply_external_update(update)
        except Exception as exc:
            self._error = f"Playback stopped: {exc}"
        finally:
            self._busy = False
        if self.driver.finished or self._error is not None:
            self.set_playing(False)
        self._sync_controls()

    def _sync_controls(self) -> None:
        available = not self.driver.finished and self._error is None
        self.play_button.setText("Pause" if self._playing else "Play")
        self.play_button.setEnabled(available)
        self.step_button.setEnabled(available)
        self.playback_status.setText(self._error or self.driver.status)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel the playback timer when its window closes."""
        self.timer.stop()
        self._playing = False
        super().closeEvent(event)
