import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from srd_arena.frontends.qt.floating_labels import (
    BATTLEFIELD_FLOATING_LABEL_STYLE,
)
from srd_arena.frontends.qt.ui.encounter import BattlefieldWidget
from srd_arena.frontends.qt.ui.encounter.status_markers import StatusMarkerHit
from srd_arena.frontends.qt.theme import FANTASY_STYLESHEET


def test_qt_tooltips_match_floating_name_style() -> None:
    assert BATTLEFIELD_FLOATING_LABEL_STYLE.qt_tooltip_rule() in FANTASY_STYLESHEET


def test_real_mouse_move_shows_painted_status_marker_tooltip() -> None:
    app = QApplication.instance() or QApplication([])
    widget = BattlefieldWidget()
    widget._status_marker_hits = [
        StatusMarkerHit(
            10.0,
            10.0,
            8.0,
            "Conditions:\n- Prone",
        )
    ]
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(10.0, 10.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    widget.mouseMoveEvent(event)

    assert widget._visible_status_tooltip == "Conditions:\n- Prone"
    assert widget._status_tooltip_anchor == (10.0, 10.0)
    font = widget._floating_label_font()
    assert font.pointSize() == BATTLEFIELD_FLOATING_LABEL_STYLE.font_point_size
    assert int(font.weight()) == BATTLEFIELD_FLOATING_LABEL_STYLE.font_weight
    widget.deleteLater()
    app.processEvents()
