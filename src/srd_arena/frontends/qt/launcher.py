from __future__ import annotations
# mypy: disable-error-code="misc"

import sys
from pathlib import Path
from typing import cast

from ...content.scenarios import ScenarioInfo, list_scenarios
from ...runtime.scenario import LoadedScenario, ScenarioLoader
from .app import GameWindow, _require_pyside6
from .theme import apply_fantasy_theme

try:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMainWindow,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime
    QApplication = None  # type: ignore[assignment]
    QFont = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]


class ScenarioPickerWindow(QMainWindow):
    def __init__(self) -> None:
        _require_pyside6()
        super().__init__()
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

        scenarios = list_scenarios()
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

    def _open_scenario(self, scenario: ScenarioInfo) -> None:
        self._game_window = GameWindow(
            scenario=create_scenario(scenario.directory),
        )
        self._game_window.show()
        self.close()


def create_scenario(scenario_dir: str | Path) -> LoadedScenario:
    return ScenarioLoader().load(scenario_dir)


def run_pyside6_app() -> None:
    _require_pyside6()
    app = (
        cast(QApplication, QApplication.instance())
        if QApplication.instance()
        else QApplication(sys.argv)
    )
    apply_fantasy_theme(app)
    window = ScenarioPickerWindow()
    window.show()
    app.exec()
