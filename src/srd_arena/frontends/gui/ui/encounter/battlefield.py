"""Render the combat grid and emit pointer interactions in grid coordinates."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from srd_arena.domain.geometry import continuous_area_outline

from ....shared.models import BattlefieldCreatureView, BattlefieldView
from ...floating_labels import BATTLEFIELD_FLOATING_LABEL_STYLE
from .area_previews import (
    area_overlay_label,
    continuous_area,
    display_area_overlay,
)
from .area_previews import (
    overlay_cells as area_overlay_cells,
)
from .area_previews import (
    overlay_origin as area_overlay_origin,
)
from .movement import MOVE_DELTAS, MovementPlan
from .status_markers import (
    StatusMarkerHit,
    build_status_marker_specs,
    creature_name_label_rect,
    status_marker_hit_radius,
    status_marker_positions,
    status_marker_tooltip,
    status_tooltip_label_rect,
    target_allocation_badge_position,
)


class BattlefieldWidget(QWidget):
    """Draw a battlefield snapshot and expose map interactions to its presenter."""

    creature_clicked = Signal(str, bool)
    cell_clicked = Signal(int, int)
    point_clicked = Signal(float, float)
    interaction_cancelled = Signal()
    BASE_CELL_SIZE = 72
    MINIMUM_HEIGHT = 320
    MIN_ZOOM = 1.0
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.15

    def __init__(self, *, image_root: Path | None = None):
        super().__init__()
        self._image_root = image_root
        self._battlefield: BattlefieldView | None = None
        self._creature_positions: dict[str, tuple[float, float, float]] = {}
        self._status_marker_hits: list[StatusMarkerHit] = []
        self._visible_status_tooltip: str | None = None
        self._status_tooltip_anchor: tuple[float, float] | None = None
        self._targetable_creature_refs: set[str] = set()
        self._selected_creature_ref: str | None = None
        self._target_allocation_counts: dict[str, int] = {}
        self._targeting_label: str | None = None
        self._area_overlay: Mapping[str, object] | None = None
        self._hover_cell: tuple[int, int] | None = None
        self._hover_point: tuple[float, float] | None = None
        self._board_metrics: tuple[float, float, float, int, int] | None = None
        self._cell_targeting_enabled = False
        self._image_cache: dict[str, QPixmap | None] = {}
        self._zoom = self.MIN_ZOOM
        self._pan_offset = (0.0, 0.0)
        self._pan_anchor: tuple[float, float] | None = None
        self._show_team_outlines = True
        self._always_show_creature_names = False
        self._movement_plan: MovementPlan | None = None
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
        dimensions_changed = self._battlefield is not None and (
            self._battlefield.width != battlefield.width
            or self._battlefield.height != battlefield.height
        )
        if dimensions_changed:
            self._zoom = self.MIN_ZOOM
            self._pan_offset = (0.0, 0.0)
        self._battlefield = battlefield
        self._creature_positions = {}
        self._invalidate_status_marker_hits()
        self.update()

    def set_area_overlay(self, area: Mapping[str, object] | None) -> None:
        self._area_overlay = area
        if self._battlefield is not None:
            self.set_battlefield(self._battlefield)
            return
        self.update()

    def set_targeting_state(
        self,
        targetable_creature_refs: set[str],
        selected_creature_ref: str | None = None,
        allocation_counts: dict[str, int] | None = None,
        targeting_label: str | None = None,
    ) -> None:
        self._targetable_creature_refs = set(targetable_creature_refs)
        self._selected_creature_ref = selected_creature_ref
        self._target_allocation_counts = dict(allocation_counts or {})
        self._targeting_label = targeting_label
        self.update()

    def set_cell_targeting_enabled(self, enabled: bool) -> None:
        self._cell_targeting_enabled = enabled
        self._update_cursor()

    def set_team_outlines_visible(self, visible: bool) -> None:
        self._show_team_outlines = visible
        self.update()

    def set_always_show_creature_names(self, visible: bool) -> None:
        self._always_show_creature_names = visible
        self.update()

    def set_movement_plan(self, plan: MovementPlan | None) -> None:
        self._movement_plan = plan
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # pragma: no cover
        if self._battlefield is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        cols = max(1, self._battlefield.width)
        rows = max(1, self._battlefield.height)
        fitted_cell_size = min(rect.width() / cols, rect.height() / rows)
        cell_size = fitted_cell_size * self._zoom
        board_width = cell_size * cols
        board_height = cell_size * rows
        self._pan_offset = self._clamped_pan_offset(
            rect,
            board_width,
            board_height,
        )
        origin_x = rect.x() + (rect.width() - board_width) / 2 + self._pan_offset[0]
        origin_y = rect.y() + (rect.height() - board_height) / 2 + self._pan_offset[1]
        self._board_metrics = (origin_x, origin_y, cell_size, cols, rows)
        display_overlay = display_area_overlay(
            self._area_overlay,
            self._hover_point,
            self._battlefield,
        )

        board_x = int(origin_x)
        board_y = int(origin_y)
        board_width_px = int(board_width)
        board_height_px = int(board_height)
        background = self._content_image(self._battlefield.background_image)
        if background is None:
            painter.fillRect(
                board_x,
                board_y,
                board_width_px,
                board_height_px,
                QColor("#303030"),
            )
        else:
            painter.drawPixmap(
                board_x,
                board_y,
                board_width_px,
                board_height_px,
                background,
            )

        grid_color = QColor(self._battlefield.grid_color)
        if not grid_color.isValid():
            grid_color = QColor("#d3d3d3")
        grid_color.setAlphaF(min(max(self._battlefield.grid_opacity, 0.0), 1.0))
        grid_pen = QPen(grid_color)
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for y in range(rows):
            for x in range(cols):
                cell_x = origin_x + x * cell_size
                cell_y = origin_y + y * cell_size
                painter.drawRect(
                    int(cell_x), int(cell_y), int(cell_size), int(cell_size)
                )

        if self._show_team_outlines:
            for creature in self._battlefield.creatures:
                cell_x = origin_x + creature.position.x * cell_size
                cell_y = origin_y + creature.position.y * cell_size
                team_color = QColor(creature.team_color)
                team_color.setAlphaF(0.7)
                team_pen = QPen(team_color)
                team_pen.setWidth(max(2, int(cell_size * 0.05)))
                painter.setPen(team_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                inset = max(1, team_pen.width() // 2)
                painter.drawRect(
                    int(cell_x + inset),
                    int(cell_y + inset),
                    max(1, int(cell_size - inset * 2)),
                    max(1, int(cell_size - inset * 2)),
                )

        movement_paths = self._movement_plan.paths if self._movement_plan else {}
        if movement_paths:
            painter.setPen(Qt.PenStyle.NoPen)
            for cell_x, cell_y in movement_paths:
                if not movement_paths[(cell_x, cell_y)]:
                    continue
                draw_x = origin_x + cell_x * cell_size
                draw_y = origin_y + cell_y * cell_size
                painter.fillRect(
                    int(draw_x + 2),
                    int(draw_y + 2),
                    max(1, int(cell_size - 4)),
                    max(1, int(cell_size - 4)),
                    QColor(63, 127, 213, 70),
                )

        preview_path = (
            movement_paths.get(self._hover_cell)
            if self._hover_cell is not None
            else None
        )
        planner = next(
            (
                creature
                for creature in self._battlefield.creatures
                if self._movement_plan is not None
                and creature.creature_ref == self._movement_plan.creature_ref
            ),
            None,
        )
        preview_cells: list[tuple[int, int]] = []
        if planner is not None and preview_path:
            preview_x = planner.position.x
            preview_y = planner.position.y
            preview_cells.append((preview_x, preview_y))
            for direction in preview_path:
                delta_x, delta_y = MOVE_DELTAS[direction]
                preview_x += delta_x
                preview_y += delta_y
                preview_cells.append((preview_x, preview_y))
            path_pen = QPen(QColor(218, 235, 255, 210))
            path_pen.setWidth(max(2, int(cell_size * 0.06)))
            painter.setPen(path_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(
                            origin_x + (path_x + 0.5) * cell_size,
                            origin_y + (path_y + 0.5) * cell_size,
                        )
                        for path_x, path_y in preview_cells
                    ]
                )
            )

        overlay_cells = area_overlay_cells(display_overlay)
        overlay_origin = area_overlay_origin(display_overlay)
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
            continuous = continuous_area(display_overlay)
            if continuous is not None:
                outline = continuous_area_outline(continuous)
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

        self._creature_positions = {}
        self._status_marker_hits = []
        for creature in self._battlefield.creatures:
            center_x = origin_x + (creature.position.x + 0.5) * cell_size
            center_y = origin_y + (creature.position.y + 0.5) * cell_size
            radius = max(14, int(cell_size * 0.38))
            fill, border = self._fallback_token_colors(creature.team_color)
            self._creature_positions[creature.creature_ref] = (
                center_x,
                center_y,
                radius,
            )

            if creature.is_active:
                painter.setBrush(QColor(255, 215, 0, 70))
                painter.setPen(Qt.PenStyle.NoPen)
                highlight_radius = int(radius * 1.6)
                painter.drawEllipse(
                    int(center_x - highlight_radius),
                    int(center_y - highlight_radius),
                    highlight_radius * 2,
                    highlight_radius * 2,
                )

            if creature.creature_ref in self._targetable_creature_refs:
                painter.setBrush(QColor(84, 196, 110, 70))
                painter.setPen(QPen(QColor("#2d7a3d"), 2))
                target_radius = int(radius * 1.3)
                painter.drawEllipse(
                    int(center_x - target_radius),
                    int(center_y - target_radius),
                    target_radius * 2,
                    target_radius * 2,
                )

            if creature.creature_ref == self._selected_creature_ref:
                painter.setBrush(QColor(255, 255, 255, 0))
                painter.setPen(QPen(QColor("#1b1b1b"), 3))
                selected_radius = int(radius * 1.45)
                painter.drawEllipse(
                    int(center_x - selected_radius),
                    int(center_y - selected_radius),
                    selected_radius * 2,
                    selected_radius * 2,
                )

            token = self._token_image(creature.token_image)
            if token is not None:
                maximum_size = cell_size * 0.98
                scale = min(
                    maximum_size / token.width(),
                    maximum_size / token.height(),
                )
                sprite_width = max(1, int(token.width() * scale))
                sprite_height = max(1, int(token.height() * scale))
                painter.drawPixmap(
                    int(center_x - sprite_width / 2),
                    int(center_y + cell_size / 2 - sprite_height),
                    sprite_width,
                    sprite_height,
                    token,
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
                    creature.label[:1].upper(),
                )

            allocation_count = self._target_allocation_counts.get(
                creature.creature_ref,
                0,
            )
            if allocation_count:
                badge_radius = max(9, int(cell_size * 0.16))
                badge_x, badge_y = target_allocation_badge_position(
                    center_x=center_x,
                    center_y=center_y,
                    token_radius=radius,
                    top_right_reserved=bool(creature.debuffs),
                )
                painter.setBrush(QColor("#f4d35e"))
                painter.setPen(QPen(QColor("#4b3900"), 2))
                painter.drawEllipse(
                    int(badge_x - badge_radius),
                    int(badge_y - badge_radius),
                    badge_radius * 2,
                    badge_radius * 2,
                )
                painter.setPen(QColor("#211900"))
                font = QFont()
                font.setBold(True)
                font.setPointSize(max(8, int(cell_size * 0.13)))
                painter.setFont(font)
                painter.drawText(
                    int(badge_x - badge_radius),
                    int(badge_y - badge_radius),
                    badge_radius * 2,
                    badge_radius * 2,
                    Qt.AlignmentFlag.AlignCenter,
                    f"x{allocation_count}",
                )

            if self._always_show_creature_names or self._hover_cell == (
                creature.position.x,
                creature.position.y,
            ):
                label_style = BATTLEFIELD_FLOATING_LABEL_STYLE
                painter.setFont(self._floating_label_font())
                label_x, label_y, label_width, label_height = creature_name_label_rect(
                    center_x=center_x,
                    center_y=center_y,
                    token_radius=radius,
                    cell_size=cell_size,
                    text_width=painter.fontMetrics().horizontalAdvance(
                        creature.name,
                    ),
                    text_height=painter.fontMetrics().height(),
                    horizontal_padding=label_style.horizontal_padding,
                    vertical_padding=label_style.vertical_padding,
                    viewport_width=self.width(),
                    viewport_height=self.height(),
                )
                self._paint_floating_label(
                    painter,
                    creature.name,
                    rect=(label_x, label_y, label_width, label_height),
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )

            self._paint_status_markers(
                painter,
                creature,
                cell_x=origin_x + creature.position.x * cell_size,
                cell_y=origin_y + creature.position.y * cell_size,
                center_x=center_x,
                center_y=center_y,
                token_radius=radius,
                cell_size=cell_size,
            )
        if planner is not None and len(preview_cells) > 1:
            destination_x, destination_y = preview_cells[-1]
            center_x = origin_x + (destination_x + 0.5) * cell_size
            center_y = origin_y + (destination_y + 0.5) * cell_size
            token = self._token_image(planner.token_image)
            painter.setOpacity(0.45)
            if token is not None:
                maximum_size = cell_size * 0.98
                scale = min(
                    maximum_size / token.width(),
                    maximum_size / token.height(),
                )
                sprite_width = max(1, int(token.width() * scale))
                sprite_height = max(1, int(token.height() * scale))
                painter.drawPixmap(
                    int(center_x - sprite_width / 2),
                    int(center_y + cell_size / 2 - sprite_height),
                    sprite_width,
                    sprite_height,
                    token,
                )
            else:
                radius = max(14, int(cell_size * 0.38))
                fill, border = self._fallback_token_colors(planner.team_color)
                painter.setBrush(fill)
                painter.setPen(QPen(border, 2))
                painter.drawEllipse(
                    int(center_x - radius),
                    int(center_y - radius),
                    radius * 2,
                    radius * 2,
                )
            painter.setOpacity(1.0)

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
                area_overlay_label(display_overlay),
            )

        if self._targeting_label is not None:
            badge_rect = rect.adjusted(12, 12, -12, -12)
            badge_height = 34
            badge_width = min(
                max(260, int(cell_size * 6.5)),
                badge_rect.width(),
            )
            painter.setBrush(QColor(37, 30, 14, 225))
            painter.setPen(QPen(QColor("#d4ad45"), 2))
            painter.drawRoundedRect(
                badge_rect.x(),
                badge_rect.y(),
                badge_width,
                badge_height,
                10,
                10,
            )
            painter.setPen(QColor("#fff4cf"))
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
                self._targeting_label,
            )

        self._paint_status_tooltip(painter)

        painter.end()

    @staticmethod
    def _floating_label_font() -> QFont:
        style = BATTLEFIELD_FLOATING_LABEL_STYLE
        font = QFont()
        font.setWeight(QFont.Weight(style.font_weight))
        font.setPointSize(style.font_point_size)
        return font

    def _paint_floating_label(
        self,
        painter: QPainter,
        text: str,
        *,
        rect: tuple[float, float, float, float],
        alignment: Qt.AlignmentFlag,
    ) -> None:
        style = BATTLEFIELD_FLOATING_LABEL_STYLE
        label_x, label_y, label_width, label_height = rect
        painter.save()
        painter.setFont(self._floating_label_font())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*style.background_rgba))
        painter.drawRoundedRect(
            int(label_x),
            int(label_y),
            int(label_width),
            int(label_height),
            style.corner_radius,
            style.corner_radius,
        )
        painter.setPen(QColor(style.foreground))
        painter.drawText(
            int(label_x + style.horizontal_padding),
            int(label_y + style.vertical_padding),
            max(1, int(label_width - style.horizontal_padding * 2)),
            max(1, int(label_height - style.vertical_padding * 2)),
            alignment,
            text,
        )
        painter.restore()

    def _paint_status_tooltip(self, painter: QPainter) -> None:
        text = self._visible_status_tooltip
        anchor = self._status_tooltip_anchor
        if text is None or anchor is None:
            return
        style = BATTLEFIELD_FLOATING_LABEL_STYLE
        painter.setFont(self._floating_label_font())
        metrics = painter.fontMetrics()
        lines = text.splitlines() or [""]
        label_rect = status_tooltip_label_rect(
            anchor_x=anchor[0],
            anchor_y=anchor[1],
            text_width=max(metrics.horizontalAdvance(line) for line in lines),
            text_height=metrics.height() * len(lines),
            horizontal_padding=style.horizontal_padding,
            vertical_padding=style.vertical_padding,
            viewport_width=self.width(),
            viewport_height=self.height(),
        )
        self._paint_floating_label(
            painter,
            text,
            rect=label_rect,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

    def _paint_status_markers(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
        *,
        cell_x: float,
        cell_y: float,
        center_x: float,
        center_y: float,
        token_radius: float,
        cell_size: float,
    ) -> None:
        specs = build_status_marker_specs(creature)
        if not specs:
            return
        positions, marker_radius = status_marker_positions(
            cell_x=cell_x,
            cell_y=cell_y,
            center_x=center_x,
            center_y=center_y,
            token_radius=token_radius,
            cell_size=cell_size,
        )
        outline_width = max(1, min(3, int(cell_size * 0.025)))
        hit_radius = status_marker_hit_radius(marker_radius)
        for spec in specs:
            marker_x, marker_y = positions[spec.corner]
            painter.setBrush(QColor(spec.color))
            painter.setPen(QPen(QColor("#161616"), outline_width))
            painter.drawEllipse(
                int(marker_x - marker_radius),
                int(marker_y - marker_radius),
                max(1, int(marker_radius * 2)),
                max(1, int(marker_radius * 2)),
            )
            self._status_marker_hits.append(
                StatusMarkerHit(marker_x, marker_y, hit_radius, spec.tooltip)
            )

    def _hide_status_tooltip(self) -> None:
        if (
            self._visible_status_tooltip is not None
            or self._status_tooltip_anchor is not None
        ):
            self._visible_status_tooltip = None
            self._status_tooltip_anchor = None
            self.update()

    def _invalidate_status_marker_hits(self) -> None:
        self._status_marker_hits = []
        self._hide_status_tooltip()

    @staticmethod
    def _fallback_token_colors(team_color: str) -> tuple[QColor, QColor]:
        fill = QColor(team_color)
        if not fill.isValid():
            fill = QColor("#3f7fd5")
        return fill, fill.darker(180)

    def _token_image(self, image_reference: str | None) -> QPixmap | None:
        return self._content_image(image_reference)

    def _content_image(self, image_reference: str | None) -> QPixmap | None:
        if image_reference is None:
            return None
        if image_reference not in self._image_cache:
            path = (
                self._image_root / image_reference
                if self._image_root is not None
                else None
            )
            pixmap = QPixmap(str(path)) if path is not None and path.is_file() else None
            self._image_cache[image_reference] = (
                pixmap if pixmap is not None and not pixmap.isNull() else None
            )
        return self._image_cache[image_reference]

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pragma: no cover
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._interaction_is_pending()
        ):
            self.interaction_cancelled.emit()
            event.accept()
            return
        if (
            event.button() in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton}
            and self._zoom > self.MIN_ZOOM
        ):
            self._pan_anchor = (event.position().x(), event.position().y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self._point_at_pixel(event.position().x(), event.position().y())
        if self._cell_targeting_enabled and point is not None:
            self.point_clicked.emit(point[0], point[1])
            return
        cell = self._cell_at_point(event.position().x(), event.position().y())
        if cell is not None:
            self.cell_clicked.emit(cell[0], cell[1])
        for creature_ref, (
            center_x,
            center_y,
            radius,
        ) in self._creature_positions.items():
            dx = event.position().x() - center_x
            dy = event.position().y() - center_y
            if dx * dx + dy * dy <= radius * radius:
                remove_allocation = bool(
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                )
                self.creature_clicked.emit(creature_ref, remove_allocation)
                break
        super().mousePressEvent(event)

    def _interaction_is_pending(self) -> bool:
        return bool(
            (self._movement_plan is not None and self._movement_plan.paths)
            or self._targetable_creature_refs
            or self._cell_targeting_enabled
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # pragma: no cover
        if self._pan_anchor is not None:
            self._invalidate_status_marker_hits()
            current = (event.position().x(), event.position().y())
            delta_x = current[0] - self._pan_anchor[0]
            delta_y = current[1] - self._pan_anchor[1]
            self._pan_offset = (
                self._pan_offset[0] + delta_x,
                self._pan_offset[1] + delta_y,
            )
            self._pan_anchor = current
            self.update()
            event.accept()
            return
        hovered_tooltip = status_marker_tooltip(
            self._status_marker_hits,
            event.position().x(),
            event.position().y(),
        )
        if hovered_tooltip != self._visible_status_tooltip:
            self._visible_status_tooltip = hovered_tooltip
            self._status_tooltip_anchor = (
                (event.position().x(), event.position().y())
                if hovered_tooltip is not None
                else None
            )
            self.update()
        previous_hover = self._hover_cell
        previous_point = self._hover_point
        self._hover_cell = self._cell_at_point(
            event.position().x(), event.position().y()
        )
        self._hover_point = self._point_at_pixel(
            event.position().x(), event.position().y()
        )
        if self._hover_cell != previous_hover or self._hover_point != previous_point:
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # pragma: no cover
        if self._pan_anchor is not None and event.button() in {
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        }:
            self._pan_anchor = None
            self._update_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # pragma: no cover
        if self._battlefield is None or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        old_metrics = self._board_metrics
        if old_metrics is None:
            return
        old_origin_x, old_origin_y, old_cell_size, _, _ = old_metrics
        cursor_x = event.position().x()
        cursor_y = event.position().y()
        board_x = (cursor_x - old_origin_x) / old_cell_size
        board_y = (cursor_y - old_origin_y) / old_cell_size
        zoom_factor = (
            self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
        )
        new_zoom = min(max(self._zoom * zoom_factor, self.MIN_ZOOM), self.MAX_ZOOM)
        if new_zoom == self._zoom:
            event.accept()
            return

        self._zoom = new_zoom
        self._invalidate_status_marker_hits()
        if self._zoom == self.MIN_ZOOM:
            self._pan_offset = (0.0, 0.0)
        else:
            rect = self.rect().adjusted(12, 12, -12, -12)
            cols = max(1, self._battlefield.width)
            rows = max(1, self._battlefield.height)
            fitted_cell_size = min(rect.width() / cols, rect.height() / rows)
            cell_size = fitted_cell_size * self._zoom
            centered_origin_x = rect.x() + (rect.width() - cell_size * cols) / 2
            centered_origin_y = rect.y() + (rect.height() - cell_size * rows) / 2
            self._pan_offset = (
                cursor_x - centered_origin_x - board_x * cell_size,
                cursor_y - centered_origin_y - board_y * cell_size,
            )
            self._pan_offset = self._clamped_pan_offset(
                rect,
                cell_size * cols,
                cell_size * rows,
            )
        self._update_cursor()
        self.update()
        event.accept()

    def _update_cursor(self) -> None:
        if self._cell_targeting_enabled:
            cursor = Qt.CursorShape.CrossCursor
        elif self._zoom > self.MIN_ZOOM:
            cursor = Qt.CursorShape.OpenHandCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def _clamped_pan_offset(
        self,
        rect: QRect,
        board_width: float,
        board_height: float,
    ) -> tuple[float, float]:
        centered_x = rect.x() + (rect.width() - board_width) / 2
        centered_y = rect.y() + (rect.height() - board_height) / 2

        def clamp_axis(
            offset: float,
            viewport_start: float,
            viewport_size: float,
            board_start: float,
            board_size: float,
        ) -> float:
            if board_size <= viewport_size:
                return 0.0
            minimum = viewport_start + viewport_size - board_size - board_start
            maximum = viewport_start - board_start
            return min(max(offset, minimum), maximum)

        return (
            clamp_axis(
                self._pan_offset[0],
                rect.x(),
                rect.width(),
                centered_x,
                board_width,
            ),
            clamp_axis(
                self._pan_offset[1],
                rect.y(),
                rect.height(),
                centered_y,
                board_height,
            ),
        )

    def leaveEvent(self, event: QEvent) -> None:  # pragma: no cover
        self._hide_status_tooltip()
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
