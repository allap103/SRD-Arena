"""Let a user choose a discovered encounter before constructing the game window."""

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

from srd_arena.content.encounters import EncounterCatalog, EncounterSummary
from srd_arena.engine.api import Session

from .app import GameWindow
from .presenter import GamePresenter
from .theme import apply_fantasy_theme


class EncounterPickerWindow(QMainWindow):
    """Display loadable encounters and launch the selected game configuration."""

    def __init__(
        self,
        catalog: EncounterCatalog,
        *,
        image_root: Path | None = None,
        pause_between_automatic_actions: bool = True,
    ) -> None:
        super().__init__()
        self._catalog = catalog
        self._image_root = image_root
        self._pause_between_automatic_actions = pause_between_automatic_actions
        self._game_window: GameWindow | None = None
        self.setWindowTitle("Choose Encounter")
        self.resize(520, 420)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Choose an encounter")
        title.setObjectName("windowTitle")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("Start a new session from any available encounter.")
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        encounters = self._catalog.available_encounters()
        if not encounters:
            empty = QLabel("No valid encounters were found in content/encounters/.")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        for encounter in encounters:
            button = QPushButton(encounter.label)
            button.setObjectName("sidebarButton")
            button.setMinimumHeight(44)
            button.clicked.connect(
                lambda _checked=False, selected=encounter: self._open_encounter(
                    selected
                )
            )
            layout.addWidget(button)
        layout.addStretch(1)

    def _open_encounter(self, encounter: EncounterSummary) -> None:
        self._game_window = GameWindow(
            GamePresenter(Session(self._catalog.load_encounter(encounter.id))),
            image_root=self._image_root,
            presentation_config=encounter.presentation,
            pause_between_automatic_actions=self._pause_between_automatic_actions,
        )
        self._game_window.show()
        self.close()


def run_gui(
    catalog: EncounterCatalog,
    *,
    image_root: Path | None = None,
    pause_between_automatic_actions: bool = True,
) -> None:
    """Start Qt, present encounter discovery, and enter the desktop event loop.

    Automatic actions are separated by a short presentation delay unless
    ``pause_between_automatic_actions`` is disabled. The engine itself always
    resolves actions immediately.
    """

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    apply_fantasy_theme(app)
    window = EncounterPickerWindow(
        catalog,
        image_root=image_root,
        pause_between_automatic_actions=pause_between_automatic_actions,
    )
    window.show()
    app.exec()
