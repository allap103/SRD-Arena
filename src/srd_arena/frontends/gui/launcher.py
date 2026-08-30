"""Let a user choose a discovered scenario before constructing the game window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from srd_arena.application.api import GameStartup, ScenarioSummary

from .app import GameWindow
from .presenter import GamePresenter
from .theme import apply_fantasy_theme


class ScenarioPickerWindow(QMainWindow):
    """Display loadable scenarios and launch the selected game configuration."""

    def __init__(
        self,
        startup: GameStartup,
        *,
        image_root: Path | None = None,
        pace_automatic_actions: bool = True,
    ) -> None:
        super().__init__()
        self._startup = startup
        self._image_root = image_root
        self._pace_automatic_actions = pace_automatic_actions
        self._game_window: GameWindow | None = None
        self.setWindowTitle("Choose Scenario")
        self.resize(520, 420)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Choose a scenario")
        title.setObjectName("windowTitle")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("Start a new session from any available scenario.")
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        scenarios = self._startup.available_scenarios()
        if not scenarios:
            empty = QLabel("No valid scenarios were found in app/content/scenarios/.")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        for scenario in scenarios:
            button = QPushButton(scenario.label)
            button.setObjectName("sidebarButton")
            button.setMinimumHeight(44)
            button.clicked.connect(
                lambda _checked=False, selected=scenario: self._open_scenario(selected)
            )
            layout.addWidget(button)
        layout.addStretch(1)

    def _open_scenario(self, scenario: ScenarioSummary) -> None:
        self._game_window = GameWindow(
            GamePresenter(
                self._startup.start_scenario(
                    scenario.id,
                    pace_automatic_actions=self._pace_automatic_actions,
                )
            ),
            image_root=self._image_root,
            presentation_config=scenario.presentation,
            pace_automatic_actions=self._pace_automatic_actions,
        )
        self._game_window.show()
        self.close()


def run_gui(
    startup: GameStartup,
    *,
    image_root: Path | None = None,
    pace_automatic_actions: bool = True,
) -> None:
    """Start Qt, present scenario discovery, and enter the desktop event loop."""

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    apply_fantasy_theme(app)
    window = ScenarioPickerWindow(
        startup,
        image_root=image_root,
        pace_automatic_actions=pace_automatic_actions,
    )
    window.show()
    app.exec()
