from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .engine import GAME_DIR, Game
from .dice_presentation import RollView, build_roll_views, without_roll_details
from .presentation import BattlefieldView, MOVE_DIRECTIONS, SessionPresentation, build_session_presentation
from .session import (
    ActionView,
    EXIT_CHOICE_TEXT,
    LOAD_CHOICE_TEXT,
    LONG_REST_CHOICE_TEXT,
    SAVE_CHOICE_TEXT,
    SHORT_REST_CHOICE_TEXT,
    GameSession,
)

try:
    from PySide6.QtCore import QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime
    def Signal(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    QApplication = None  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    QColor = object  # type: ignore[assignment]
    QFont = object  # type: ignore[assignment]
    QPainter = object  # type: ignore[assignment]
    QPen = object  # type: ignore[assignment]
    QPixmap = object  # type: ignore[assignment]
    QSvgRenderer = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QGridLayout = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QScrollArea = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QStackedWidget = object  # type: ignore[assignment]
    QTextEdit = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]


SIDEBAR_WIDTH = 220
ARROW_LABELS = {
    "up-left": "↖",
    "up": "↑",
    "up-right": "↗",
    "left": "←",
    "right": "→",
    "down-left": "↙",
    "down": "↓",
    "down-right": "↘",
}


def _require_pyside6() -> None:
    if QApplication is None:
        raise RuntimeError(
            "PySide6 is not installed. Install project dependencies including PySide6 to use this frontend."
        )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


@dataclass(frozen=True)
class TargetSelectionMode:
    kind: str
    source_trigger_id: str | None = None


@dataclass(frozen=True)
class ActionMenuScope:
    economy: str
    bucket: str


class DieSvgWidget(QWidget):
    SIZE = 58

    def __init__(self, sides: int, value: int, *, selected: bool = True):
        super().__init__()
        self._value = value
        self._selected = selected
        svg_path = Path(__file__).parent / "assets" / "dice" / f"d{sides}.svg"
        self._renderer = QSvgRenderer(str(svg_path))
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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


class DiceRollPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self._has_content = False

    def clear_log(self) -> None:
        _clear_layout(self._layout)
        self._layout.addStretch(1)
        self._has_content = False

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

    def append_entry(
        self,
        messages: list[tuple[str, str]],
        rolls: list[RollView],
    ) -> None:
        if not messages and not rolls:
            return

        entry = QWidget()
        entry_layout = QVBoxLayout(entry)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        entry_layout.setSpacing(6)
        if messages:
            message_label = QLabel("\n".join(message for _, message in messages))
            message_label.setWordWrap(True)
            entry_layout.addWidget(message_label)
        for roll in rolls:
            entry_layout.addWidget(self._build_roll_row(roll))
        self._insert_widget(entry)
        self._has_content = True

    def _insert_widget(self, widget: QWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)

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
                die_widget = DieSvgWidget(die_sides, die.value, selected=die.selected)
                die_widget.setToolTip(
                    " -> ".join(str(value) for value in die.history)
                    if die.history
                    else f"Rolled {die.value}"
                )
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


class BattlefieldWidget(QWidget):
    actor_clicked = Signal(str)
    BASE_CELL_SIZE = 72
    MINIMUM_HEIGHT = 320

    def __init__(self, game_dir: str | Path = GAME_DIR):
        super().__init__()
        self._battlefield: BattlefieldView | None = None
        self._actor_positions: dict[str, tuple[float, float, float]] = {}
        self._targetable_actor_refs: set[str] = set()
        self._selected_actor_ref: str | None = None
        self._sprites_dir = Path(game_dir) / "sprites"
        self._sprite_cache: dict[str, QPixmap | None] = {}
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        if self._battlefield is None:
            return QSize(600, 420)
        return QSize(
            self._battlefield.width * self.BASE_CELL_SIZE + 24,
            self._battlefield.height * self.BASE_CELL_SIZE + 24,
        )

    def set_battlefield(self, battlefield: BattlefieldView) -> None:
        self._battlefield = battlefield
        self._actor_positions = {}
        self.update()

    def set_targeting_state(
        self,
        targetable_actor_refs: set[str],
        selected_actor_ref: str | None = None,
    ) -> None:
        self._targetable_actor_refs = set(targetable_actor_refs)
        self._selected_actor_ref = selected_actor_ref
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - GUI painting
        if self._battlefield is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        cols = max(1, self._battlefield.width)
        rows = max(1, self._battlefield.height)
        cell_size = min(rect.width() / cols, rect.height() / rows)
        board_width = cell_size * cols
        board_height = cell_size * rows
        origin_x = rect.x() + (rect.width() - board_width) / 2
        origin_y = rect.y() + (rect.height() - board_height) / 2

        grid_pen = QPen(QColor("#c8b68c"))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for y in range(rows):
            for x in range(cols):
                fill = QColor("#f4ecd8") if (x + y) % 2 == 0 else QColor("#eadfbe")
                cell_x = origin_x + x * cell_size
                cell_y = origin_y + y * cell_size
                painter.fillRect(int(cell_x), int(cell_y), int(cell_size), int(cell_size), fill)
                painter.drawRect(int(cell_x), int(cell_y), int(cell_size), int(cell_size))

        self._actor_positions = {}
        for actor in self._battlefield.actors:
            center_x = origin_x + (actor.position.x + 0.5) * cell_size
            center_y = origin_y + (actor.position.y + 0.5) * cell_size
            radius = max(14, int(cell_size * 0.38))
            fill = QColor("#2e6f95") if actor.is_player else QColor("#b34a3c")
            border = QColor("#17364a") if actor.is_player else QColor("#5a1f18")
            self._actor_positions[actor.actor_ref] = (center_x, center_y, radius)

            if actor.is_active:
                painter.setBrush(QColor(255, 215, 0, 70))
                painter.setPen(Qt.PenStyle.NoPen)
                highlight_radius = int(radius * 1.6)
                painter.drawEllipse(
                    int(center_x - highlight_radius),
                    int(center_y - highlight_radius),
                    highlight_radius * 2,
                    highlight_radius * 2,
                )

            if actor.actor_ref in self._targetable_actor_refs:
                painter.setBrush(QColor(84, 196, 110, 70))
                painter.setPen(QPen(QColor("#2d7a3d"), 2))
                target_radius = int(radius * 1.3)
                painter.drawEllipse(
                    int(center_x - target_radius),
                    int(center_y - target_radius),
                    target_radius * 2,
                    target_radius * 2,
                )

            if actor.actor_ref == self._selected_actor_ref:
                painter.setBrush(QColor(255, 255, 255, 0))
                painter.setPen(QPen(QColor("#1b1b1b"), 3))
                selected_radius = int(radius * 1.45)
                painter.drawEllipse(
                    int(center_x - selected_radius),
                    int(center_y - selected_radius),
                    selected_radius * 2,
                    selected_radius * 2,
                )

            sprite = self._sprite_for_actor(actor.actor_id, actor.label)
            if sprite is not None:
                sprite_size = int(cell_size * 0.82)
                painter.drawPixmap(
                    int(center_x - sprite_size / 2),
                    int(center_y - sprite_size / 2),
                    sprite_size,
                    sprite_size,
                    sprite,
                )
            else:
                painter.setBrush(fill)
                painter.setPen(QPen(border, 2))
                painter.drawEllipse(
                    int(center_x - radius),
                    int(center_y - radius),
                    radius * 2,
                    radius * 2,
                )

                painter.setPen(QColor("white"))
                font = QFont()
                font.setBold(True)
                font.setPointSize(max(8, int(cell_size * 0.18)))
                painter.setFont(font)
                painter.drawText(
                    int(center_x - radius),
                    int(center_y - radius),
                    radius * 2,
                    radius * 2,
                    Qt.AlignmentFlag.AlignCenter,
                    actor.label[:1].upper(),
                )

        painter.end()

    def _sprite_for_actor(self, actor_id: str, label: str) -> QPixmap | None:
        for name in self._sprite_names(actor_id, label):
            if name not in self._sprite_cache:
                path = self._sprites_dir / name
                pixmap = QPixmap(str(path)) if path.exists() else None
                self._sprite_cache[name] = pixmap if pixmap is not None and not pixmap.isNull() else None
            if self._sprite_cache[name] is not None:
                return self._sprite_cache[name]
        return None

    def _sprite_names(self, actor_id: str, label: str) -> list[str]:
        names = [f"{actor_id}.png"]
        label_name = label.split("(")[-1].rstrip(")") if "(" in label else label
        slug = label_name.strip().lower().replace(" ", "_")
        if slug:
            names.append(f"{slug}.png")
        return names

    def mousePressEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        for actor_ref, (center_x, center_y, radius) in self._actor_positions.items():
            dx = event.position().x() - center_x
            dy = event.position().y() - center_y
            if dx * dx + dy * dy <= radius * radius:
                self.actor_clicked.emit(actor_ref)
                break
        super().mousePressEvent(event)


class CyoaPySide6Window(QMainWindow):
    def __init__(self, game: Game | None = None):
        _require_pyside6()
        super().__init__()
        self.game = game or Game(GAME_DIR)
        self.session: GameSession = self.game.create_session()
        self._items_by_id = {item.id: item for item in self.game.items}
        self._presentation: SessionPresentation | None = None
        self._pending_target_mode: TargetSelectionMode | None = None
        self._action_menu_scope: ActionMenuScope | None = None
        self._combat_log_scene_id: str | None = None
        self._logged_round_number: int | None = None

        self.setWindowTitle("CYOA")
        self.resize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_main_content(), stretch=1)
        root_layout.addWidget(self._build_sidebar())

        self.refresh_view()

    def _build_main_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.scene_group = self._build_group("Scene")
        self.scene_text = self._build_readonly_text(minimum_height=180)
        self.scene_group.layout().addWidget(self.scene_text)

        self.story_choices_group = self._build_group("Choices")
        self.story_choices_layout = QVBoxLayout()
        self.story_choices_layout.setSpacing(8)
        story_scroll = self._wrap_in_scroll(self.story_choices_layout)
        self.story_choices_group.layout().addWidget(story_scroll)

        self.encounter_panel = QWidget()
        encounter_layout = QVBoxLayout(self.encounter_panel)
        encounter_layout.setContentsMargins(0, 0, 0, 0)
        encounter_layout.setSpacing(10)

        battlefield_area = QWidget()
        battlefield_layout = QHBoxLayout(battlefield_area)
        battlefield_layout.setContentsMargins(0, 0, 0, 0)
        battlefield_layout.setSpacing(10)

        self.battlefield_widget = BattlefieldWidget(self.game.directory)
        self.battlefield_widget.actor_clicked.connect(self._handle_battlefield_actor_clicked)
        battlefield_layout.addWidget(self.battlefield_widget, stretch=1)

        roll_rail = QFrame()
        roll_rail.setFrameShape(QFrame.Shape.StyledPanel)
        roll_rail.setFixedWidth(310)
        roll_rail_layout = QVBoxLayout(roll_rail)
        roll_rail_layout.setContentsMargins(10, 10, 10, 10)
        roll_rail_layout.setSpacing(8)
        roll_title = QLabel("Combat Log")
        roll_title.setStyleSheet("QLabel { font-weight: 700; }")
        roll_rail_layout.addWidget(roll_title)

        self.dice_roll_panel = DiceRollPanel()
        self.roll_scroll = QScrollArea()
        self.roll_scroll.setWidgetResizable(True)
        self.roll_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.roll_scroll.setWidget(self.dice_roll_panel)
        roll_rail_layout.addWidget(self.roll_scroll, stretch=1)
        battlefield_layout.addWidget(roll_rail)

        encounter_layout.addWidget(battlefield_area, stretch=1)

        encounter_controls = QWidget()
        encounter_controls.setFixedHeight(280)
        encounter_controls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        encounter_controls_layout = QHBoxLayout(encounter_controls)
        encounter_controls_layout.setContentsMargins(0, 0, 0, 0)
        encounter_controls_layout.setSpacing(10)

        self.movement_group = self._build_group("Movement")
        self.movement_buttons: dict[str, QPushButton] = {}
        movement_grid = QGridLayout()
        movement_grid.setSpacing(6)
        positions = {
            "up-left": (0, 0),
            "up": (0, 1),
            "up-right": (0, 2),
            "left": (1, 0),
            "right": (1, 2),
            "down-left": (2, 0),
            "down": (2, 1),
            "down-right": (2, 2),
        }
        for direction in MOVE_DIRECTIONS:
            button = QPushButton(ARROW_LABELS[direction])
            button.setMinimumHeight(46)
            button.clicked.connect(
                lambda _checked=False, move_direction=direction: self._trigger_move(move_direction)
            )
            self.movement_buttons[direction] = button
            row, col = positions[direction]
            movement_grid.addWidget(button, row, col)
        movement_center = QLabel("Move")
        movement_center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        movement_grid.addWidget(movement_center, 1, 1)
        self.movement_group.layout().addLayout(movement_grid)
        self.movement_group.setFixedWidth(210)
        encounter_controls_layout.addWidget(self.movement_group)

        self.encounter_actions_group = self._build_untitled_panel()
        self.encounter_actions_layout = QHBoxLayout()
        self.encounter_actions_layout.setSpacing(12)
        self.encounter_actions_group.layout().addWidget(
            self._wrap_in_scroll(self.encounter_actions_layout)
        )
        actions_footer = QWidget()
        actions_footer_layout = QHBoxLayout(actions_footer)
        actions_footer_layout.setContentsMargins(0, 0, 0, 0)
        actions_footer_layout.addStretch(1)
        self.end_turn_button = QPushButton("End Turn")
        self.end_turn_button.clicked.connect(self._end_turn)
        actions_footer_layout.addWidget(self.end_turn_button)
        self.encounter_actions_group.layout().addWidget(actions_footer)
        encounter_controls_layout.addWidget(self.encounter_actions_group, stretch=1)

        encounter_layout.addWidget(encounter_controls)

        layout.addWidget(self.scene_group, stretch=1)
        layout.addWidget(self.story_choices_group, stretch=1)
        layout.addWidget(self.encounter_panel, stretch=2)
        return container

    def _build_sidebar(self) -> QWidget:
        sidebar = self._framed_panel("Menu")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = sidebar.layout()

        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.addWidget(self._build_sidebar_root())
        self.sidebar_stack.addWidget(self._build_inventory_page())
        self.sidebar_stack.addWidget(self._build_attributes_page())
        self.sidebar_stack.addWidget(self._build_system_page())
        layout.addWidget(self.sidebar_stack)
        return sidebar

    def _build_sidebar_root(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Attributes", self.show_attributes))
        layout.addWidget(self._sidebar_button("Inventory", self.show_inventory))
        layout.addWidget(self._sidebar_button("System", self.show_system_menu))
        layout.addStretch(1)
        self.short_rest_button = self._sidebar_button(
            SHORT_REST_CHOICE_TEXT,
            lambda: self._trigger_rest("system_short_rest"),
        )
        self.long_rest_button = self._sidebar_button(
            LONG_REST_CHOICE_TEXT,
            lambda: self._trigger_rest("system_long_rest"),
        )
        layout.addWidget(self.short_rest_button)
        layout.addWidget(self.long_rest_button)
        return page

    def _build_inventory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        self.inventory_text = self._build_readonly_text(minimum_height=400)
        layout.addWidget(self.inventory_text, stretch=1)
        return page

    def _build_attributes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        self.attributes_text = self._build_readonly_text(minimum_height=400)
        layout.addWidget(self.attributes_text, stretch=1)
        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        layout.addWidget(self._sidebar_button(SAVE_CHOICE_TEXT, self._system_save))
        layout.addWidget(self._sidebar_button(LOAD_CHOICE_TEXT, self._system_load))
        layout.addWidget(self._sidebar_button(EXIT_CHOICE_TEXT, self.close))
        layout.addStretch(1)
        return page

    def _build_group(self, title: str) -> QFrame:
        group = QFrame()
        group.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        return group

    def _framed_panel(self, title: str) -> QFrame:
        panel = self._build_group(title)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        return panel

    def _build_untitled_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        return panel

    def _wrap_in_scroll(self, content_layout: QVBoxLayout) -> QScrollArea:
        container = QWidget()
        container.setLayout(content_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        return scroll

    def _build_readonly_text(
        self,
        minimum_height: int = 100,
        maximum_height: int | None = None,
    ) -> QTextEdit:
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(minimum_height)
        if maximum_height is not None:
            text.setMaximumHeight(maximum_height)
        return text

    def _sidebar_button(self, label: str, callback) -> QPushButton:
        button = QPushButton(label)
        button.clicked.connect(callback)
        return button

    def refresh_view(self) -> None:
        presentation = build_session_presentation(self.session)
        self._presentation = presentation
        if presentation.encounter is None:
            self._pending_target_mode = None
            self._action_menu_scope = None

        self.scene_text.setPlainText(presentation.story_text or "")
        self._sync_rest_buttons(presentation)

        if presentation.encounter is None:
            self.scene_group.show()
            self.story_choices_group.show()
            self.encounter_panel.hide()
            self._render_story_actions(presentation.story_actions)
        else:
            self.scene_group.hide()
            self.story_choices_group.hide()
            self.encounter_panel.show()
            self._sync_combat_log_round(presentation.scene_id)
            self._render_encounter(presentation)

    def _render_story_actions(self, actions: list[ActionView]) -> None:
        _clear_layout(self.story_choices_layout)
        for action in actions:
            if action.kind in {"system_short_rest", "system_long_rest"}:
                continue
            button = QPushButton(action.label)
            button.clicked.connect(
                lambda _checked=False, action_index=action.index: self._select_action(action_index)
            )
            self.story_choices_layout.addWidget(button)
        self.story_choices_layout.addStretch(1)

    def _render_encounter(self, presentation: SessionPresentation) -> None:
        encounter = presentation.encounter
        assert encounter is not None
        self.battlefield_widget.set_battlefield(encounter.battlefield)

        target_modes = self._target_selection_modes(encounter.non_movement_actions)
        if self._pending_target_mode not in target_modes:
            self._pending_target_mode = None
        selected_targetable_actions = (
            target_modes.get(self._pending_target_mode, {}) if self._pending_target_mode is not None else {}
        )
        targetable_refs = {
            target_ref
            for action in selected_targetable_actions.values()
            if (target_ref := self._target_actor_ref(action)) is not None
        }
        self.battlefield_widget.set_targeting_state(targetable_refs)

        for direction, button in self.movement_buttons.items():
            action = encounter.movement_actions.get(direction)
            button.setEnabled(action is not None)

        action_groups = self._action_groups(encounter.non_movement_actions)
        if self._action_menu_scope is not None and encounter.action_pane_title == "Reactions":
            self._action_menu_scope = None
        if (
            self._action_menu_scope is not None
            and not action_groups.get(self._action_menu_scope.economy, {}).get(
                self._action_menu_scope.bucket,
            )
        ):
            self._action_menu_scope = None

        _clear_layout(self.encounter_actions_layout)
        rendered_target_modes: set[TargetSelectionMode] = set()
        if encounter.action_pane_title == "Reactions":
            self._render_action_detail_column(
                "Reaction",
                encounter.non_movement_actions,
                rendered_target_modes,
                scope=None,
            )
            self.encounter_actions_layout.addStretch(1)
        else:
            self._render_action_economy_column(
                title="Actions",
                economy="action",
                bucket_actions=action_groups["action"],
                available=encounter.resources.action_status == "Ready",
                rendered_target_modes=rendered_target_modes,
                indicator_color="#2f6f9d",
            )
            self._render_action_economy_column(
                title="Bonus Actions",
                economy="bonus_action",
                bucket_actions=action_groups["bonus_action"],
                available=encounter.resources.bonus_action_status == "Ready",
                rendered_target_modes=rendered_target_modes,
                indicator_color="#c9a227",
            )
            self._render_feature_column(encounter.feature_actions, rendered_target_modes)
            self._render_status_column(encounter.resources)

        if encounter.end_turn_action is None:
            self.end_turn_button.setEnabled(False)
            self.end_turn_button.setText("End Turn")
        else:
            self.end_turn_button.setEnabled(True)
            self.end_turn_button.setText(
                "Pass Reaction" if encounter.end_turn_action.kind == "pass" else "End Turn"
            )

    def _render_action_economy_column(
        self,
        title: str,
        economy: str,
        bucket_actions: dict[str, list[ActionView]],
        available: bool,
        rendered_target_modes: set[TargetSelectionMode],
        indicator_color: str,
    ) -> None:
        if self._action_menu_scope is not None and self._action_menu_scope.economy == economy:
            self._render_action_detail_column(
                self._action_scope_title(self._action_menu_scope),
                bucket_actions[self._action_menu_scope.bucket],
                rendered_target_modes,
                scope=self._action_menu_scope,
            )
            return
        self._render_action_menu_column(title, economy, bucket_actions, available, indicator_color)

    def _render_action_menu_column(
        self,
        title: str,
        economy: str,
        bucket_actions: dict[str, list[ActionView]],
        available: bool,
        indicator_color: str,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        column_layout.addWidget(self._build_action_header(title, available, indicator_color))

        for bucket_key, bucket_title in self._action_buckets():
            actions = bucket_actions[bucket_key]
            button = QPushButton(bucket_title)
            button.setEnabled(bool(actions))
            button.clicked.connect(
                lambda _checked=False, selected_economy=economy, selected_bucket=bucket_key: (
                    self._open_action_menu(selected_economy, selected_bucket)
                )
            )
            column_layout.addWidget(button)

        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_action_detail_column(
        self,
        title: str,
        actions: list[ActionView],
        rendered_target_modes: set[TargetSelectionMode],
        scope: ActionMenuScope | None,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        header = QLabel(title)
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        column_layout.addWidget(header)

        if not actions:
            empty = QLabel("None")
            empty.setEnabled(False)
            column_layout.addWidget(empty)
        for action in actions:
            button = self._build_encounter_action_button(action, rendered_target_modes)
            if button is not None:
                column_layout.addWidget(button)
        column_layout.addStretch(1)
        if scope is not None:
            back = QPushButton("Back")
            back.clicked.connect(lambda _checked=False, selected_scope=scope: self._close_action_menu(selected_scope))
            column_layout.addWidget(back)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_feature_column(
        self,
        feature_actions: list[ActionView],
        rendered_target_modes: set[TargetSelectionMode],
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        header = QLabel("Class Features")
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        column_layout.addWidget(header)

        if not feature_actions:
            empty = QLabel("None")
            empty.setEnabled(False)
            column_layout.addWidget(empty)
        else:
            for action in feature_actions:
                widget = self._build_feature_action_widget(action, rendered_target_modes)
                if widget is not None:
                    column_layout.addWidget(widget)

        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_status_column(self, resources) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        header = QLabel("Status")
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        column_layout.addWidget(header)
        column_layout.addWidget(
            self._build_resource_bar(
                "Health",
                resources.current_health,
                resources.max_health,
                "#9d2f2f",
                f"{resources.current_health}/{resources.max_health}",
            )
        )
        column_layout.addWidget(
            self._build_resource_bar(
                "Movement",
                resources.movement_remaining_feet,
                resources.movement_total_feet,
                "#2f6f9d",
                f"{resources.movement_remaining_feet}/{resources.movement_total_feet} ft",
            )
        )
        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _build_action_header(self, title: str, available: bool, indicator_color: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        indicator = QFrame()
        indicator.setFixedSize(10, 10)
        if available:
            indicator.setStyleSheet(
                f"QFrame {{ background: {indicator_color}; border: 1px solid {indicator_color}; border-radius: 5px; }}"
            )
        else:
            indicator.setStyleSheet(
                "QFrame { background: transparent; border: 1px solid #8a806a; border-radius: 5px; }"
            )
        layout.addWidget(indicator)

        header = QLabel(title)
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)
        layout.addStretch(1)
        return container

    def _build_resource_bar(
        self,
        label: str,
        current: int,
        maximum: int,
        color: str,
        value_text: str,
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        title = QLabel(label)
        layout.addWidget(title)

        bar = QFrame()
        bar.setMinimumHeight(24)
        bar.setStyleSheet(
            "QFrame {"
            "border: 1px solid #9c8b68;"
            "background: #efe4c8;"
            "border-radius: 4px;"
            "}"
        )
        bar_layout = QGridLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)
        filled = QFrame()
        filled.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 3px; }}")
        empty = QFrame()
        empty.setStyleSheet("QFrame { background: transparent; }")
        filled_units = max(0, min(current, maximum))
        empty_units = max(0, maximum - filled_units)
        bar_layout.addWidget(filled, 0, 0)
        bar_layout.addWidget(empty, 0, 1)
        bar_layout.setColumnStretch(0, max(filled_units, 1 if maximum == 0 else 0))
        bar_layout.setColumnStretch(1, max(empty_units, 1 if maximum == 0 else 0))
        value = QLabel(value_text, bar)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setStyleSheet("QLabel { color: white; font-weight: bold; background: transparent; }")
        bar_layout.addWidget(value, 0, 0, 1, 2)
        layout.addWidget(bar)
        return container

    def _build_encounter_action_button(
        self,
        action: ActionView,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QPushButton | None:
        target_mode = self._target_mode_for_action(action)
        if target_mode is not None:
            if target_mode in rendered_target_modes:
                return None
            rendered_target_modes.add(target_mode)
            button = QPushButton(self._target_mode_label(target_mode))
            button.setCheckable(True)
            button.setChecked(target_mode == self._pending_target_mode)
            if action.index < 0:
                button.setEnabled(False)
                return button
            button.clicked.connect(
                lambda _checked=False, mode=target_mode: self._toggle_target_action(mode)
            )
            return button

        button = QPushButton(action.label)
        if action.index < 0:
            button.setEnabled(False)
            return button
        button.clicked.connect(
            lambda _checked=False, action_index=action.index: self._select_action(action_index)
        )
        return button

    def _build_feature_action_widget(
        self,
        action: ActionView,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QWidget | None:
        button = self._build_encounter_action_button(action, rendered_target_modes)
        if button is None:
            return None
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        indicator = QFrame()
        indicator.setFixedSize(10, 10)
        if action.cost.get("bonus_action", 0) > 0:
            indicator.setStyleSheet(
                "QFrame { background: #c9a227; border: 1px solid #c9a227; border-radius: 5px; }"
            )
        else:
            indicator.setStyleSheet(
                "QFrame { background: #9c8b68; border: 1px solid #9c8b68; border-radius: 5px; }"
            )
        layout.addWidget(indicator)
        layout.addWidget(button, stretch=1)
        return container

    def _action_groups(
        self,
        actions: list[ActionView],
    ) -> dict[str, dict[str, list[ActionView]]]:
        groups = {
            economy: {bucket: [] for bucket, _ in self._action_buckets()}
            for economy in ("action", "bonus_action", "reaction")
        }
        for action in actions:
            groups[self._action_economy_key(action)][self._action_bucket_key(action)].append(action)
        return groups

    def _action_buckets(self) -> tuple[tuple[str, str], ...]:
        return (
            ("attack", "Attack"),
            ("magic", "Magic"),
            ("class", "Class"),
            ("utilize", "Utilize"),
            ("other", "Other"),
        )

    def _open_action_menu(self, economy: str, bucket: str) -> None:
        self._pending_target_mode = None
        self._action_menu_scope = ActionMenuScope(economy=economy, bucket=bucket)
        self.refresh_view()

    def _close_action_menu(self, scope: ActionMenuScope | None = None) -> None:
        self._pending_target_mode = None
        if scope is not None and self._action_menu_scope != scope:
            return
        self._action_menu_scope = None
        self.refresh_view()

    def _action_scope_title(self, scope: ActionMenuScope) -> str:
        economy_title = "Bonus Actions" if scope.economy == "bonus_action" else "Actions"
        bucket_title = dict(self._action_buckets())[scope.bucket]
        return f"{economy_title} / {bucket_title}"

    def _action_economy_key(self, action: ActionView) -> str:
        if action.cost.get("bonus_action", 0) > 0:
            return "bonus_action"
        if action.cost.get("reaction", 0) > 0 or action.kind in {"opportunity_attack", "pass"}:
            return "reaction"
        return "action"

    def _action_bucket_key(self, action: ActionView) -> str:
        if action.kind in {"attack", "opportunity_attack"}:
            return "attack"
        if action.kind == "magic":
            return "magic"
        if action.kind == "feature":
            return "class"
        if action.kind == "utilize":
            return "utilize"
        return "other"

    def _trigger_move(self, direction: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        action = self._presentation.encounter.movement_actions.get(direction)
        if action is not None:
            self._select_action(action.index)

    def _end_turn(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        action = self._presentation.encounter.end_turn_action
        if action is not None:
            self._select_action(action.index)

    def _system_save(self) -> None:
        if self._presentation is None:
            return
        self._select_action(self._presentation.system_actions[0].index)

    def _system_load(self) -> None:
        if self._presentation is None:
            return
        self._select_action(self._presentation.system_actions[1].index)

    def _trigger_rest(self, kind: str) -> None:
        if self._presentation is None or self._presentation.encounter is not None:
            return
        action = next(
            (action for action in self._presentation.story_actions if action.kind == kind),
            None,
        )
        if action is not None:
            self._select_action(action.index)

    def _sync_rest_buttons(self, presentation: SessionPresentation) -> None:
        if not hasattr(self, "short_rest_button"):
            return
        if presentation.encounter is not None:
            self.short_rest_button.hide()
            self.long_rest_button.hide()
            return
        rest_actions = {action.kind: action for action in presentation.story_actions}
        short_rest_action = rest_actions.get("system_short_rest")
        long_rest_action = rest_actions.get("system_long_rest")
        self.short_rest_button.setVisible(short_rest_action is not None)
        self.long_rest_button.setVisible(long_rest_action is not None)
        self.short_rest_button.setEnabled(short_rest_action is not None)
        self.long_rest_button.setEnabled(long_rest_action is not None)

    def _select_action(self, index: int) -> None:
        self._pending_target_mode = None
        self._action_menu_scope = None
        result = self.session.choose(index)
        self._apply_turn_result(result)

    def _toggle_target_action(self, mode: TargetSelectionMode) -> None:
        self._pending_target_mode = None if self._pending_target_mode == mode else mode
        self.refresh_view()

    def _handle_battlefield_actor_clicked(self, actor_ref: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        if self._pending_target_mode is None:
            return
        action = self._target_selection_modes(self._presentation.encounter.non_movement_actions).get(
            self._pending_target_mode,
            {},
        ).get(
            actor_ref
        )
        if action is None:
            return
        self._select_action(action.index)

    def _target_selection_modes(
        self,
        actions: list[ActionView],
    ) -> dict[TargetSelectionMode, dict[str, ActionView]]:
        modes: dict[TargetSelectionMode, dict[str, ActionView]] = {}
        for action in actions:
            target_mode = self._target_mode_for_action(action)
            target_actor_ref = self._target_actor_ref(action)
            if target_mode is None or target_actor_ref is None:
                continue
            modes.setdefault(target_mode, {})[target_actor_ref] = action
        return modes

    def _target_mode_for_action(self, action: ActionView) -> TargetSelectionMode | None:
        if self._target_actor_ref(action) is None:
            return None
        return TargetSelectionMode(
            kind=action.kind,
            source_trigger_id=action.source_trigger_id,
        )

    def _target_mode_label(self, mode: TargetSelectionMode) -> str:
        return "Opportunity attack" if mode.kind == "opportunity_attack" else "Attack"

    def _target_actor_ref(self, action: ActionView | None) -> str | None:
        if action is None or action.kind not in {"attack", "opportunity_attack"}:
            return None
        if not isinstance(action.value, int):
            return None
        return f"enemy:{action.value}"

    def _apply_turn_result(self, result) -> None:
        encounter_state = self.session.encounter_state
        was_in_encounter = (
            self._presentation is not None and self._presentation.encounter is not None
        )
        is_combat_result = was_in_encounter or encounter_state is not None
        if (
            encounter_state is not None
            and self._combat_log_scene_id != encounter_state.scene_id
        ):
            self._sync_combat_log_round(encounter_state.scene_id)
        if is_combat_result:
            roll_views = build_roll_views(result.events)
            messages = without_roll_details(result.messages)
            self.dice_roll_panel.append_entry(messages, roll_views)
            if messages or roll_views:
                QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

        if result.should_exit:
            self.close()
            return
        self.refresh_view()

    def _sync_combat_log_round(self, scene_id: str) -> None:
        encounter_state = self.session.encounter_state
        if encounter_state is None:
            return
        if self._combat_log_scene_id != scene_id:
            self.dice_roll_panel.clear_log()
            self._combat_log_scene_id = scene_id
            self._logged_round_number = None
        if self._logged_round_number == encounter_state.round_number:
            return
        self.dice_roll_panel.start_round(encounter_state.round_number)
        self._logged_round_number = encounter_state.round_number
        QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

    def _scroll_roll_log_to_bottom(self) -> None:
        scrollbar = self.roll_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_menu_root(self) -> None:
        self.sidebar_stack.setCurrentIndex(0)

    def show_inventory(self) -> None:
        items = self.session.player.inventory.items
        inventory_text = (
            "Inventory is empty."
            if not items
            else "\n".join(self.display_item_name(item_id) for item_id in items)
        )
        self.inventory_text.setPlainText(inventory_text)
        self.sidebar_stack.setCurrentIndex(1)

    def show_attributes(self) -> None:
        player = self.session.player
        attributes = player.attributes
        attributes_text = "\n".join(
            [
                f"Name: {player.name}",
                f"HP: {player.get_health()}/{player.get_max_health()}",
                f"AC: {player.get_armor_class()}",
                f"Level: {attributes.level}",
                f"STR: {attributes.strength}",
                f"DEX: {attributes.dexterity}",
                f"CON: {attributes.constitution}",
                f"WIS: {attributes.wisdom}",
                f"INT: {attributes.intelligence}",
                f"CHA: {attributes.charisma}",
                f"PB: +{attributes.proficiency_bonus}",
            ]
        )
        self.attributes_text.setPlainText(attributes_text)
        self.sidebar_stack.setCurrentIndex(2)

    def show_system_menu(self) -> None:
        self.sidebar_stack.setCurrentIndex(3)

    def display_item_name(self, item_id: str) -> str:
        item = self._items_by_id.get(item_id)
        return item.name if item else item_id


def run_pyside6_app(game: Game | None = None) -> None:
    _require_pyside6()
    app = QApplication.instance() or QApplication(sys.argv)
    window = CyoaPySide6Window(game=game)
    window.show()
    app.exec()
