"""Render the combat grid and emit pointer interactions in grid coordinates."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...presentation.models import BattlefieldView
from .area_previews import display_area_overlay
from .battlefield_renderer import (
    BattlefieldRenderer,
    BattlefieldRenderGeometry,
    BattlefieldRenderInput,
)
from .movement import MovementPlan
from .status_markers import (
    StatusMarkerHit,
    status_marker_tooltip,
)


def clamp_axis(
    offset: float,
    viewport_start: float,
    viewport_size: float,
    board_start: float,
    board_size: float,
) -> float:
    """Clamp one pan offset so a large board continues to cover the viewport.
    A board smaller than its viewport remains centered rather than pannable.
    >>> clamp_axis(20, 0, 100, 25, 50)
    0.0
    >>> clamp_axis(80, 0, 100, -50, 200)
    50
    >>> clamp_axis(-80, 0, 100, -50, 200)
    -50
    """
    if board_size <= viewport_size:
        return 0.0
    minimum = viewport_start + viewport_size - board_size - board_start
    maximum = viewport_start - board_start
    return min(max(offset, minimum), maximum)


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
        self._renderer = BattlefieldRenderer(image_root=image_root)
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
        geometry = self._render_geometry()
        display_overlay = display_area_overlay(
            self._area_overlay,
            self._hover_point,
            self._battlefield,
        )
        result = self._renderer.paint(
            painter,
            BattlefieldRenderInput(
                battlefield=self._battlefield,
                geometry=geometry,
                area_overlay=display_overlay,
                movement_plan=self._movement_plan,
                hover_cell=self._hover_cell,
                targetable_creature_refs=frozenset(self._targetable_creature_refs),
                selected_creature_ref=self._selected_creature_ref,
                target_allocation_counts=tuple(self._target_allocation_counts.items()),
                targeting_label=self._targeting_label,
                visible_status_tooltip=self._visible_status_tooltip,
                status_tooltip_anchor=self._status_tooltip_anchor,
                show_team_outlines=self._show_team_outlines,
                always_show_creature_names=self._always_show_creature_names,
                viewport_width=self.width(),
                viewport_height=self.height(),
            ),
        )
        self._creature_positions = {
            hit.creature_ref: (hit.center_x, hit.center_y, hit.radius)
            for hit in result.creature_hits
        }
        self._status_marker_hits = list(result.status_marker_hits)
        painter.end()

    def _render_geometry(self) -> BattlefieldRenderGeometry:
        """Calculate and retain the pixel geometry used by this paint pass."""

        assert self._battlefield is not None
        viewport = self.rect().adjusted(12, 12, -12, -12)
        columns = max(1, self._battlefield.width)
        rows = max(1, self._battlefield.height)
        fitted_cell_size = min(viewport.width() / columns, viewport.height() / rows)
        cell_size = fitted_cell_size * self._zoom
        board_width = cell_size * columns
        board_height = cell_size * rows
        self._pan_offset = self._clamped_pan_offset(
            viewport,
            board_width,
            board_height,
        )
        origin_x = (
            viewport.x() + (viewport.width() - board_width) / 2 + self._pan_offset[0]
        )
        origin_y = (
            viewport.y() + (viewport.height() - board_height) / 2 + self._pan_offset[1]
        )
        self._board_metrics = (
            origin_x,
            origin_y,
            cell_size,
            columns,
            rows,
        )
        return BattlefieldRenderGeometry(
            viewport=(
                viewport.x(),
                viewport.y(),
                viewport.width(),
                viewport.height(),
            ),
            origin_x=origin_x,
            origin_y=origin_y,
            cell_size=cell_size,
            columns=columns,
            rows=rows,
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
