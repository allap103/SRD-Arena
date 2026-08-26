from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ....shared.dice import RollView
from .layout import clear_layout

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class DieSvgWidget(QWidget):
    clicked = Signal(str)
    SIZE = 58

    def __init__(
        self,
        sides: int,
        value: int,
        *,
        selected: bool = True,
        action_id: str | None = None,
    ):
        super().__init__()
        self._value = value
        self._selected = selected
        self._action_id = action_id
        svg_path = Path(__file__).parents[3] / "assets" / "dice" / f"d{sides}.svg"
        self._renderer = QSvgRenderer(str(svg_path))
        self.setFixedSize(self.SIZE, self.SIZE)
        if action_id is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._action_id is not None and self.isEnabled():
            painter.setBrush(QColor("#fff3c4"))
            painter.setPen(QPen(QColor("#c9a227"), 2))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        if not self._selected:
            painter.setOpacity(0.45)
        self._renderer.render(painter, self.rect().adjusted(5, 2, -5, -2))
        painter.setOpacity(1.0)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#153638" if self._selected else "#687176"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._value))
        painter.end()

    def mousePressEvent(self, event) -> None:
        if self.isEnabled() and self._action_id is not None:
            self.clicked.emit(self._action_id)
        super().mousePressEvent(event)


class DiceRollPanel(QWidget):
    def __init__(
        self,
        action_callback: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("dicePanel")
        self._action_callback = action_callback
        self._roll_action_widgets: dict[str, list[QWidget]] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self._has_content = False

    def clear_log(self) -> None:
        clear_layout(self._layout)
        self._layout.addStretch(1)
        self._has_content = False
        self._roll_action_widgets.clear()

    def start_round(self, round_number: int) -> None:
        if self._has_content:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            self._insert_widget(separator)
        announcement = QLabel(f"Round {round_number}")
        announcement.setStyleSheet("QLabel { font-size: 15px; font-weight: 700; }")
        self._insert_widget(announcement)
        self._has_content = True

    def start_turn(self, label: str) -> None:
        announcement = QLabel(label)
        announcement.setWordWrap(True)
        announcement.setStyleSheet("QLabel { font-weight: 700; }")
        self._insert_widget(announcement)
        self._has_content = True

    def append_entry(
        self,
        messages: list[tuple[str, str]],
        rolls: list[RollView],
    ) -> None:
        if not messages and not rolls:
            return

        regular_messages: list[str] = []
        for channel, message in messages:
            if channel == "turn":
                self.start_turn(message)
            else:
                regular_messages.append(message)

        if not regular_messages and not rolls:
            return

        entry = QWidget()
        entry_layout = QVBoxLayout(entry)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        entry_layout.setSpacing(6)
        if regular_messages:
            message_label = QLabel("\n".join(regular_messages))
            message_label.setWordWrap(True)
            entry_layout.addWidget(message_label)
        for roll in rolls:
            self._disable_roll_actions(roll.roll_id)
            entry_layout.addWidget(self._build_roll_row(roll))
        self._insert_widget(entry)
        self._has_content = True

    def _insert_widget(self, widget: QWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def _disable_roll_actions(self, roll_id: str | None) -> None:
        if roll_id is None:
            return
        for widget in self._roll_action_widgets.get(roll_id, []):
            widget.setEnabled(False)
            widget.update()
        self._roll_action_widgets[roll_id] = []

    def _register_roll_action_widget(
        self,
        roll: RollView,
        widget: QWidget,
    ) -> None:
        if roll.roll_id is None:
            return
        self._roll_action_widgets.setdefault(roll.roll_id, []).append(widget)

    def _build_roll_row(self, roll: RollView) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        title = QLabel(roll.label)
        title.setWordWrap(True)
        layout.addWidget(title)

        dice_layout = QHBoxLayout()
        dice_layout.setContentsMargins(0, 0, 0, 0)
        dice_layout.setSpacing(8)
        for die in roll.dice:
            die_sides = _single_die_sides(die.expression)
            if die_sides is not None:
                die_widget = DieSvgWidget(
                    die_sides,
                    die.value,
                    selected=die.selected,
                    action_id=die.action_id,
                )
                die_widget.setToolTip(
                    "Click to reroll"
                    if die.action_id is not None
                    else " -> ".join(str(value) for value in die.history)
                    if die.history
                    else f"Rolled {die.value}"
                )
                if die.action_id is not None and self._action_callback is not None:
                    die_widget.clicked.connect(self._action_callback)
                    self._register_roll_action_widget(roll, die_widget)
                dice_layout.addWidget(die_widget)
                continue
            die_label = QLabel(f"{die.expression}\n{die.value}")
            die_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            die_label.setFixedSize(58, 52)
            die_label.setToolTip(
                " -> ".join(str(value) for value in die.history)
                if die.history
                else f"Rolled {die.value}"
            )
            border = "#167c80" if die.selected else "#8a9299"
            background = "#e8f4f3" if die.selected else "#eceff1"
            die_label.setStyleSheet(
                "QLabel {"
                f"background: {background}; border: 2px solid {border};"
                "border-radius: 6px; font-weight: 700;"
                "}"
            )
            dice_layout.addWidget(die_label)
        dice_layout.addStretch(1)
        layout.addLayout(dice_layout)

        modifier_text = f"{roll.modifier:+d}" if roll.modifier else "+0"
        summary = f"{modifier_text}  =  {roll.total}"
        if roll.target is not None:
            summary += f"  vs  {roll.target}"
        if roll.success is not None:
            summary += "   SUCCESS" if roll.success else "   FAILURE"
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("QLabel { font-weight: 600; }")
        layout.addWidget(summary_label)
        if roll.resolution_notes:
            resolution_label = QLabel("\n".join(roll.resolution_notes))
            resolution_label.setWordWrap(True)
            resolution_label.setStyleSheet(
                "QLabel { color: #8a4b08; font-weight: 600; }"
            )
            layout.addWidget(resolution_label)
        return row


def _single_die_sides(expression: str) -> int | None:
    normalized = expression.casefold()
    if normalized.startswith("1d"):
        normalized = normalized[1:]
    if not normalized.startswith("d"):
        return None
    try:
        sides = int(normalized[1:])
    except ValueError:
        return None
    return sides if sides in {4, 6, 8, 10, 12, 20} else None
