from __future__ import annotations

from pathlib import Path

from ...dice_presentation import RollView
from ...encounter_geometry import (
    Vector2D,
    build_cone_area_from_vector,
    build_cube_area_from_vector,
    build_line_area_from_vector,
    continuous_area_outline,
    deserialize_continuous_area,
    serialize_area,
)
from ...engine import GAME_DIR
from ...models.scene import Grid, Position
from ...presentation import BattlefieldView

try:
    from PySide6.QtCore import QPointF, QSize, Qt, Signal
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime
    def Signal(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    QPointF = object  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QColor = object  # type: ignore[assignment]
    QFont = object  # type: ignore[assignment]
    QPainter = object  # type: ignore[assignment]
    QPen = object  # type: ignore[assignment]
    QPixmap = object  # type: ignore[assignment]
    QPolygonF = object  # type: ignore[assignment]
    QSvgRenderer = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QGridLayout = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QScrollArea = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


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
        svg_path = Path(__file__).parents[2] / "assets" / "dice" / f"d{sides}.svg"
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
    def __init__(self, action_callback=None):
        super().__init__()
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
        return row


def spell_slot_rich_text(level: int, remaining: int, maximum: int) -> str:
    gap = "&nbsp;"
    available = gap.join(
        '<span style="color:#2f6f9d;">&#x25A0;</span>' for _ in range(remaining)
    )
    spent = gap.join(
        '<span style="color:#9d2f2f;">&#x25A0;</span>'
        for _ in range(max(0, maximum - remaining))
    )
    markers = gap.join(part for part in (available, spent) if part)
    return f"{level}: {markers}"


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
    cell_clicked = Signal(int, int)
    point_clicked = Signal(float, float)
    BASE_CELL_SIZE = 72
    MINIMUM_HEIGHT = 320

    def __init__(self, game_dir: str | Path = GAME_DIR):
        super().__init__()
        self._battlefield: BattlefieldView | None = None
        self._actor_positions: dict[str, tuple[float, float, float]] = {}
        self._targetable_actor_refs: set[str] = set()
        self._selected_actor_ref: str | None = None
        self._area_overlay: dict[str, object] | None = None
        self._hover_cell: tuple[int, int] | None = None
        self._hover_point: tuple[float, float] | None = None
        self._board_metrics: tuple[float, float, float, int, int] | None = None
        self._cell_targeting_enabled = False
        self._sprites_dir = Path(game_dir) / "sprites"
        self._sprite_cache: dict[str, QPixmap | None] = {}
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

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
        tooltip_lines = []
        for actor in battlefield.actors:
            conditions = (
                ", ".join(condition.capitalize() for condition in actor.conditions)
                if actor.conditions
                else "None"
            )
            tooltip_lines.append(f"{actor.label}: {conditions}")
        if self._area_overlay is not None:
            tooltip_lines.append(self._area_overlay_tooltip(self._area_overlay))
        self.setToolTip("\n".join(tooltip_lines))
        self.update()

    def set_area_overlay(self, area: dict[str, object] | None) -> None:
        self._area_overlay = area
        if self._battlefield is not None:
            self.set_battlefield(self._battlefield)
            return
        self.update()

    def set_targeting_state(
        self,
        targetable_actor_refs: set[str],
        selected_actor_ref: str | None = None,
    ) -> None:
        self._targetable_actor_refs = set(targetable_actor_refs)
        self._selected_actor_ref = selected_actor_ref
        self.update()

    def set_cell_targeting_enabled(self, enabled: bool) -> None:
        self._cell_targeting_enabled = enabled
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )

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
        self._board_metrics = (origin_x, origin_y, cell_size, cols, rows)
        display_overlay = self._display_area_overlay()

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

        overlay_cells = self._overlay_cells(display_overlay)
        overlay_origin = self._overlay_origin(display_overlay)
        if overlay_cells:
            painter.setPen(Qt.PenStyle.NoPen)
            for cell_x, cell_y in overlay_cells:
                draw_x = origin_x + cell_x * cell_size
                draw_y = origin_y + cell_y * cell_size
                painter.fillRect(
                    int(draw_x + 1),
                    int(draw_y + 1),
                    max(1, int(cell_size - 2)),
                    max(1, int(cell_size - 2)),
                    QColor(72, 142, 212, 95),
                )
            continuous_area = self._continuous_area(display_overlay)
            if continuous_area is not None:
                outline = continuous_area_outline(continuous_area)
                if outline is not None:
                    painter.setBrush(QColor(132, 188, 234, 55))
                    outline_pen = QPen(QColor("#1c4e80"), 2)
                    outline_pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(outline_pen)
                    painter.drawPolygon(
                        QPolygonF(
                            [
                                QPointF(
                                    origin_x + (point.x * cell_size),
                                    origin_y + (point.y * cell_size),
                                )
                                for point in outline
                            ]
                        )
                    )
            painter.setPen(QPen(QColor("#2a5f92"), 2))
            for cell_x, cell_y in overlay_cells:
                draw_x = origin_x + cell_x * cell_size
                draw_y = origin_y + cell_y * cell_size
                painter.drawRect(
                    int(draw_x + 1),
                    int(draw_y + 1),
                    max(1, int(cell_size - 2)),
                    max(1, int(cell_size - 2)),
                )

        if overlay_origin is not None:
            origin_cell_x, origin_cell_y = overlay_origin
            draw_x = origin_x + origin_cell_x * cell_size
            draw_y = origin_y + origin_cell_y * cell_size
            painter.setBrush(QColor(255, 247, 186, 110))
            painter.setPen(QPen(QColor("#9a7a17"), 3))
            painter.drawRect(
                int(draw_x + 2),
                int(draw_y + 2),
                max(1, int(cell_size - 4)),
                max(1, int(cell_size - 4)),
            )

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

        if display_overlay is not None:
            badge_rect = rect.adjusted(12, 12, -12, -12)
            badge_height = 32
            badge_width = min(int(cell_size * 3.8), max(160, badge_rect.width() // 3))
            painter.setBrush(QColor(23, 54, 74, 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                badge_rect.x(),
                badge_rect.y(),
                badge_width,
                badge_height,
                10,
                10,
            )
            painter.setPen(QColor("white"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(
                badge_rect.x() + 12,
                badge_rect.y(),
                badge_width - 24,
                badge_height,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._area_overlay_label(display_overlay),
            )

        painter.end()

    def _display_area_overlay(self) -> dict[str, object] | None:
        preview = self._preview_area_overlay(
            self._area_overlay,
            self._hover_point,
            self._battlefield,
        )
        return preview if preview is not None else self._area_overlay

    def _overlay_cells(self, area: dict[str, object] | None) -> set[tuple[int, int]]:
        if not isinstance(area, dict):
            return set()
        cells = area.get("cells")
        if not isinstance(cells, list):
            return set()
        return {
            (cell["x"], cell["y"])
            for cell in cells
            if isinstance(cell, dict)
            and isinstance(cell.get("x"), int)
            and isinstance(cell.get("y"), int)
        }

    def _overlay_origin(self, area: dict[str, object] | None) -> tuple[int, int] | None:
        if not isinstance(area, dict):
            return None
        origin = area.get("origin")
        if not isinstance(origin, dict):
            return None
        x = origin.get("x")
        y = origin.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        return (x, y)

    def _continuous_area(self, area: dict[str, object] | None):
        if not isinstance(area, dict):
            return None
        return deserialize_continuous_area(area.get("continuous_area"))

    def _area_overlay_label(self, area: dict[str, object]) -> str:
        shape = area.get("shape")
        label = str(shape).capitalize() if isinstance(shape, str) else "Area"
        return f"{label} AoE"

    def _area_overlay_tooltip(self, area: dict[str, object]) -> str:
        label = self._area_overlay_label(area)
        cell_count = len(self._overlay_cells(area))
        policy = area.get("rasterization_policy")
        if isinstance(policy, str):
            threshold = area.get("coverage_threshold")
            if isinstance(threshold, (int, float)):
                return (
                    f"{label}: {cell_count} cells "
                    f"({policy.replace('_', ' ')}, {float(threshold) * 100:.0f}% min)"
                )
            return f"{label}: {cell_count} cells ({policy.replace('_', ' ')})"
        return f"{label}: {cell_count} cells"

    @staticmethod
    def _preview_area_overlay(
        area: dict[str, object] | None,
        hover_point: tuple[float, float] | None,
        battlefield: BattlefieldView | None,
    ) -> dict[str, object] | None:
        if area is None or hover_point is None or battlefield is None:
            return None
        origin = area.get("origin")
        if not isinstance(origin, dict):
            return None
        origin_x = origin.get("x")
        origin_y = origin.get("y")
        if not isinstance(origin_x, int) or not isinstance(origin_y, int):
            return None
        continuous_area = deserialize_continuous_area(area.get("continuous_area"))
        if (
            continuous_area is None
            or continuous_area.direction is None
            or continuous_area.shape not in {"cone", "line", "cube"}
            or continuous_area.length is None
        ):
            return None
        if int(hover_point[0]) == origin_x and int(hover_point[1]) == origin_y:
            return None
        direction = Vector2D(
            hover_point[0] - continuous_area.origin.x,
            hover_point[1] - continuous_area.origin.y,
        )
        origin_position = Position(origin_x, origin_y)
        grid = Grid(width=battlefield.width, height=battlefield.height)
        size = max(1, int(round(continuous_area.length)))
        coverage_threshold = (
            continuous_area.coverage_threshold
            if continuous_area.coverage_threshold is not None
            else 0.5
        )
        if continuous_area.shape == "cone":
            return serialize_area(
                build_cone_area_from_vector(
                    origin_position,
                    direction,
                    size,
                    grid,
                    coverage_threshold=coverage_threshold,
                )
            )
        if continuous_area.shape == "line":
            return serialize_area(
                build_line_area_from_vector(
                    origin_position,
                    direction,
                    size,
                    grid,
                    coverage_threshold=coverage_threshold,
                )
            )
        if continuous_area.shape == "cube":
            return serialize_area(
                build_cube_area_from_vector(
                    origin_position,
                    direction,
                    size,
                    grid,
                    coverage_threshold=coverage_threshold,
                )
            )
        return None

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
        point = self._point_at_pixel(event.position().x(), event.position().y())
        if self._cell_targeting_enabled and point is not None:
            self.point_clicked.emit(point[0], point[1])
            return
        cell = self._cell_at_point(event.position().x(), event.position().y())
        if cell is not None:
            self.cell_clicked.emit(cell[0], cell[1])
        for actor_ref, (center_x, center_y, radius) in self._actor_positions.items():
            dx = event.position().x() - center_x
            dy = event.position().y() - center_y
            if dx * dx + dy * dy <= radius * radius:
                self.actor_clicked.emit(actor_ref)
                break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        previous_hover = self._hover_cell
        previous_point = self._hover_point
        self._hover_cell = self._cell_at_point(event.position().x(), event.position().y())
        self._hover_point = self._point_at_pixel(event.position().x(), event.position().y())
        if self._hover_cell != previous_hover or self._hover_point != previous_point:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        if self._hover_cell is not None or self._hover_point is not None:
            self._hover_cell = None
            self._hover_point = None
            self.update()
        super().leaveEvent(event)

    def _cell_at_point(self, x: float, y: float) -> tuple[int, int] | None:
        if self._board_metrics is None:
            return None
        origin_x, origin_y, cell_size, cols, rows = self._board_metrics
        if x < origin_x or y < origin_y:
            return None
        col = int((x - origin_x) // cell_size)
        row = int((y - origin_y) // cell_size)
        if not (0 <= col < cols and 0 <= row < rows):
            return None
        return (col, row)

    def _point_at_pixel(self, x: float, y: float) -> tuple[float, float] | None:
        if self._board_metrics is None:
            return None
        origin_x, origin_y, cell_size, cols, rows = self._board_metrics
        local_x = (x - origin_x) / cell_size
        local_y = (y - origin_y) / cell_size
        if not (0.0 <= local_x <= cols and 0.0 <= local_y <= rows):
            return None
        return (local_x, local_y)
