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
    def __init__(
        self,
        start_scene_override: str | None = None,
        *,
        control_mode: str = "default",
        show_encounter_json: bool = False,
    ):
        _require_pyside6()
        super().__init__()
        self._start_scene_override = start_scene_override
        self._control_mode = control_mode
        self._show_encounter_json = show_encounter_json
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
            scenario=create_scenario(
                scenario.directory,
                start_scene_override=self._start_scene_override,
                control_mode=self._control_mode,
            ),
            show_encounter_json=self._show_encounter_json,
        )
        self._game_window.show()
        self.close()


def create_scenario(
    scenario_dir: str | Path,
    *,
    start_scene_override: str | None,
    control_mode: str,
) -> LoadedScenario:
    return ScenarioLoader().load(
        scenario_dir,
        start_scene=start_scene_override,
        control_mode=control_mode,
    )


def run_pyside6_app(
    scenario_dir: str | Path | None = None,
    start_scene_override: str | None = None,
    control_mode: str = "default",
    show_encounter_json: bool = False,
) -> None:
    _require_pyside6()
    app = (
        cast(QApplication, QApplication.instance())
        if QApplication.instance()
        else QApplication(sys.argv)
    )
    apply_fantasy_theme(app)
    window = (
        GameWindow(
            scenario=create_scenario(
                scenario_dir,
                start_scene_override=start_scene_override,
                control_mode=control_mode,
            ),
            show_encounter_json=show_encounter_json,
        )
        if scenario_dir is not None
        else ScenarioPickerWindow(
            start_scene_override=start_scene_override,
            control_mode=control_mode,
            show_encounter_json=show_encounter_json,
        )
    )
    window.show()
    app.exec()
