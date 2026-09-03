"""Let a user choose a discovered encounter before constructing the game window."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from srd_arena.content.encounters import EncounterCatalog, EncounterSummary
from srd_arena.engine.api import Session, SessionFactory

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
        session_factory: SessionFactory | None = None,
    ) -> None:
        super().__init__()
        self._catalog = catalog
        self._image_root = image_root
        self._pause_between_automatic_actions = pause_between_automatic_actions
        self._session_factory = session_factory or Session
        self._game_window: GameWindow | None = None
        self._encounters_by_id: dict[str, EncounterSummary] = {}
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

        encounters = sorted(
            self._catalog.available_encounters(),
            key=lambda encounter: (
                encounter.label.casefold(),
                encounter.label,
                encounter.id,
            ),
        )
        if not encounters:
            empty = QLabel("No valid encounters were found in content/encounters/.")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        self._encounters_by_id = {encounter.id: encounter for encounter in encounters}
        tree = QTreeWidget()
        tree.setObjectName("encounterTree")
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setIndentation(22)
        tree.itemClicked.connect(self._activate_tree_item)
        self._populate_tree(tree, encounters)
        layout.addWidget(tree, 1)

    def _populate_tree(
        self,
        tree: QTreeWidget,
        encounters: list[EncounterSummary],
    ) -> None:
        """Populate root encounters and recursively nested collapsed folders."""

        for encounter in _sorted_encounters(
            candidate for candidate in encounters if not candidate.folder
        ):
            tree.addTopLevelItem(self._encounter_item(encounter))
        root_folders = sorted(
            {encounter.folder[0] for encounter in encounters if encounter.folder},
            key=lambda name: (name.casefold(), name),
        )
        for folder_name in root_folders:
            self._add_folder_item(tree, None, (folder_name,), encounters)

    def _add_folder_item(
        self,
        tree: QTreeWidget,
        parent: QTreeWidgetItem | None,
        folder: tuple[str, ...],
        encounters: list[EncounterSummary],
    ) -> None:
        """Add one collapsed folder and recursively populate its descendants."""

        item = QTreeWidgetItem([_folder_label(folder[-1])])
        item.setData(0, Qt.ItemDataRole.UserRole, None)
        if parent is None:
            tree.addTopLevelItem(item)
        else:
            parent.addChild(item)

        child_names = sorted(
            {
                encounter.folder[len(folder)]
                for encounter in encounters
                if len(encounter.folder) > len(folder)
                and encounter.folder[: len(folder)] == folder
            },
            key=lambda name: (name.casefold(), name),
        )
        for child_name in child_names:
            self._add_folder_item(
                tree,
                item,
                (*folder, child_name),
                encounters,
            )
        for encounter in _sorted_encounters(
            candidate for candidate in encounters if candidate.folder == folder
        ):
            item.addChild(self._encounter_item(encounter))
        item.setExpanded(False)

    def _encounter_item(self, encounter: EncounterSummary) -> QTreeWidgetItem:
        """Create a selectable tree leaf for one encounter summary."""

        item = QTreeWidgetItem([encounter.label])
        item.setData(0, Qt.ItemDataRole.UserRole, encounter.id)
        return item

    def _activate_tree_item(self, item: QTreeWidgetItem, _column: int) -> None:
        """Open an encounter leaf while leaving folder behavior to Qt."""

        encounter_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(encounter_id, str):
            return
        encounter = self._encounters_by_id.get(encounter_id)
        if encounter is not None:
            self._open_encounter(encounter)

    def _open_encounter(self, encounter: EncounterSummary) -> None:
        try:
            definition = self._catalog.load_encounter(encounter.id)
        except (KeyError, OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                "Unable to load encounter",
                str(error),
            )
            return
        self._game_window = GameWindow(
            GamePresenter(self._session_factory(definition)),
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
    session_factory: SessionFactory | None = None,
) -> None:
    """Start Qt, present encounter discovery, and enter the desktop event loop.

    Automatic actions are separated by a short presentation delay unless
    ``pause_between_automatic_actions`` is disabled. The engine itself always
    resolves actions immediately. ``session_factory`` lets the composition
    root supply configured sessions without exposing engine setup to the GUI.
    """

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    apply_fantasy_theme(app)
    window = EncounterPickerWindow(
        catalog,
        image_root=image_root,
        pause_between_automatic_actions=pause_between_automatic_actions,
        session_factory=session_factory,
    )
    window.show()
    app.exec()


def _sorted_encounters(
    encounters: Iterable[EncounterSummary],
) -> list[EncounterSummary]:
    """Return encounter summaries in stable human-facing label order."""

    return sorted(
        encounters,
        key=lambda encounter: (
            encounter.label.casefold(),
            encounter.label,
            encounter.id,
        ),
    )


def _folder_label(name: str) -> str:
    """Turn an authored directory name into a readable picker label."""

    return name.replace("_", " ").replace("-", " ").title()
