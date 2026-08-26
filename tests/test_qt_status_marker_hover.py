import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from srd_arena.frontends.qt.ui.encounter import widgets
from srd_arena.frontends.qt.ui.encounter.status_markers import StatusMarkerHit


def test_real_mouse_move_shows_status_marker_tooltip(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    shown: list[str] = []

    class FakeToolTip:
        @staticmethod
        def showText(_position, tooltip, _parent) -> None:
            shown.append(tooltip)

        @staticmethod
        def hideText() -> None:
            pass

    monkeypatch.setattr(widgets, "QToolTip", FakeToolTip)
    widget = widgets.BattlefieldWidget()
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

    assert shown == ["Conditions:\n- Prone"]
    widget.deleteLater()
    app.processEvents()
