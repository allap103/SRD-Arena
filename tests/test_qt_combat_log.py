"""The combat log stays live and inspectable when moved between windows."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session
from srd_arena.frontends.gui.app import GameWindow
from srd_arena.frontends.gui.presenter import GamePresenter


@pytest.fixture
def game() -> Iterator[tuple[QApplication, GameWindow]]:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication([])
    window = GameWindow(
        GamePresenter(Session(EncounterCatalog().load_encounter("warlock_training"))),
        manage_automatic_actions=False,
    )
    window.resize(1400, 900)
    window.show()
    app.processEvents()
    try:
        yield app, window
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("close_action", ["close", "reject", "button"])
def test_live_log_moves_back_without_losing_history(
    game: tuple[QApplication, GameWindow], close_action: str
) -> None:
    app, window = game
    sidebar = window.sidebar
    sidebar.append_combat_log([("info", "Before opening")], [])
    panel = sidebar._dice_roll_panel
    sidebar._pop_out_log_button.click()
    app.processEvents()
    popup = sidebar._log_window
    assert popup is not None and popup.isVisible()
    assert not popup.isModal()
    assert sidebar._log_body.parentWidget() is popup
    assert sidebar._dice_roll_panel is panel
    sidebar.pop_out_combat_log()
    assert sidebar._log_window is popup
    sidebar.append_combat_log([("info", "While detached")], [])
    labels = panel.findChildren(QLabel)
    assert {"Before opening", "While detached"} <= {label.text() for label in labels}
    assert all(
        label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        for label in labels
    )
    if close_action == "button":
        button = popup.findChild(QPushButton)
        assert button is not None
        button.click()
    elif close_action == "reject":
        popup.reject()  # Escape uses QDialog.reject.
    else:
        popup.close()
    app.processEvents()
    assert not popup.isVisible()
    assert sidebar._log_body.parentWidget() is not popup
    assert sidebar._log_body.isVisible()
    assert not sidebar._log_placeholder.isVisible()
    assert "While detached" in {label.text() for label in panel.findChildren(QLabel)}
    sidebar.pop_out_combat_log()
    assert sidebar._log_window is popup
    window.close()
    assert not popup.isVisible()


def test_pausing_follow_preserves_reading_position(
    game: tuple[QApplication, GameWindow],
) -> None:
    app, window = game
    sidebar = window.sidebar
    for index in range(100):
        sidebar.append_combat_log([("info", f"Log entry {index}")], [])
    sidebar.pop_out_combat_log()
    app.processEvents()
    app.processEvents()
    scrollbar = sidebar._roll_scroll.verticalScrollBar()
    assert scrollbar.maximum() > 100
    sidebar._follow_log.setChecked(False)
    scrollbar.setValue(100)
    sidebar.append_combat_log([("info", "New arrival")], [])
    app.processEvents()
    sidebar.scroll_combat_log_to_bottom()
    assert scrollbar.value() == 100
    sidebar.close_combat_log_window()
    app.processEvents()
    app.processEvents()
    assert scrollbar.value() == 100
    sidebar.pop_out_combat_log()
    app.processEvents()
    app.processEvents()
    assert scrollbar.value() == 100
    sidebar._follow_log.setChecked(True)
    assert scrollbar.value() == scrollbar.maximum()
