"""Initiative-track widget for the Qt battlefield surface."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....shared.models import InitiativeTrackEntryView
from .layout import clear_layout


class InitiativeRail(QFrame):
    """Own and render the encounter initiative order."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("rollRail")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        title = QLabel("Initiative")
        title.setObjectName("initiativeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._entries_layout = QVBoxLayout(content)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(4)
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

    def set_entries(self, entries: Sequence[InitiativeTrackEntryView]) -> None:
        """Replace the displayed initiative order with one snapshot."""

        clear_layout(self._entries_layout)
        if not entries:
            empty = QLabel("No initiative order.")
            empty.setEnabled(False)
            self._entries_layout.addWidget(empty)
            self._entries_layout.addStretch(1)
            return

        for entry in entries:
            card = QFrame()
            card.setObjectName("initiativeCard")
            card.setProperty("active", entry.is_active)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 7, 10, 7)
            card_layout.setSpacing(2)
            name = QLabel(entry.name)
            name.setObjectName("initiativeName")
            name.setWordWrap(True)
            card_layout.addWidget(name)
            score = QLabel(str(entry.total))
            score.setObjectName("initiativeScore")
            card_layout.addWidget(score)
            self._entries_layout.addWidget(card)
        self._entries_layout.addStretch(1)
