"""Paint the battlefield board, movement previews, and area geometry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

from srd_arena.domain.geometry import continuous_area_outline

from ...presentation.models import BattlefieldCreatureView, BattlefieldView
from .area_previews import continuous_area
from .area_previews import overlay_cells as area_overlay_cells
from .area_previews import overlay_origin as area_overlay_origin
from .movement import MOVE_DELTAS, MovementPlan

ImageLoader = Callable[[str | None], QPixmap | None]
TokenColors = Callable[[str], tuple[QColor, QColor]]


class BoardGeometry(Protocol):
    """Provide the pixel geometry needed by board paint phases."""

    @property
    def origin_x(self) -> float:
        """Return the board's horizontal pixel origin."""

    @property
    def origin_y(self) -> float:
        """Return the board's vertical pixel origin."""

    @property
    def cell_size(self) -> float:
        """Return the rendered size of one grid cell."""

    @property
    def columns(self) -> int:
        """Return the number of rendered grid columns."""

    @property
    def rows(self) -> int:
        """Return the number of rendered grid rows."""

    @property
    def board_width(self) -> float:
        """Return the rendered board width in pixels."""

    @property
    def board_height(self) -> float:
        """Return the rendered board height in pixels."""


@dataclass(frozen=True)
class MovementPreview:
    """Hold the creature and cells in the currently previewed movement path."""

    creature: BattlefieldCreatureView | None
    cells: tuple[tuple[int, int], ...]


def paint_board(
    painter: QPainter,
    battlefield: BattlefieldView,
    geometry: BoardGeometry,
    load_image: ImageLoader,
) -> None:
    """Paint the board background and square grid."""

    background = load_image(battlefield.background_image)
    if background is None:
        painter.fillRect(
            int(geometry.origin_x),
            int(geometry.origin_y),
            int(geometry.board_width),
            int(geometry.board_height),
            QColor("#303030"),
        )
    else:
        painter.drawPixmap(
            int(geometry.origin_x),
            int(geometry.origin_y),
            int(geometry.board_width),
            int(geometry.board_height),
            background,
        )

    grid_color = QColor(battlefield.grid_color)
    if not grid_color.isValid():
        grid_color = QColor("#d3d3d3")
    grid_color.setAlphaF(min(max(battlefield.grid_opacity, 0.0), 1.0))
    grid_pen = QPen(grid_color)
    grid_pen.setWidth(1)
    painter.setPen(grid_pen)
    for y in range(geometry.rows):
        for x in range(geometry.columns):
            cell_x = geometry.origin_x + x * geometry.cell_size
            cell_y = geometry.origin_y + y * geometry.cell_size
            painter.drawRect(
                int(cell_x),
                int(cell_y),
                int(geometry.cell_size),
                int(geometry.cell_size),
            )


def paint_team_outlines(
    painter: QPainter,
    battlefield: BattlefieldView,
    geometry: BoardGeometry,
    *,
    visible: bool,
) -> None:
    """Paint team-colored outlines around occupied cells when enabled."""

    if not visible:
        return
    for creature in battlefield.creatures:
        cell_x = geometry.origin_x + creature.position.x * geometry.cell_size
        cell_y = geometry.origin_y + creature.position.y * geometry.cell_size
        team_color = QColor(creature.team_color)
        team_color.setAlphaF(0.7)
        team_pen = QPen(team_color)
        team_pen.setWidth(max(2, int(geometry.cell_size * 0.05)))
        painter.setPen(team_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = max(1, team_pen.width() // 2)
        painter.drawRect(
            int(cell_x + inset),
            int(cell_y + inset),
            max(1, int(geometry.cell_size - inset * 2)),
            max(1, int(geometry.cell_size - inset * 2)),
        )


def paint_movement_plan(
    painter: QPainter,
    battlefield: BattlefieldView,
    geometry: BoardGeometry,
    movement_plan: MovementPlan | None,
    hover_cell: tuple[int, int] | None,
) -> MovementPreview:
    """Paint reachable cells and the currently hovered movement path."""

    movement_paths = movement_plan.paths if movement_plan else {}
    if movement_paths:
        painter.setPen(Qt.PenStyle.NoPen)
        for cell_x, cell_y in movement_paths:
            if not movement_paths[(cell_x, cell_y)]:
                continue
            draw_x = geometry.origin_x + cell_x * geometry.cell_size
            draw_y = geometry.origin_y + cell_y * geometry.cell_size
            painter.fillRect(
                int(draw_x + 2),
                int(draw_y + 2),
                max(1, int(geometry.cell_size - 4)),
                max(1, int(geometry.cell_size - 4)),
                QColor(63, 127, 213, 70),
            )

    preview_path = movement_paths.get(hover_cell) if hover_cell is not None else None
    planner = next(
        (
            creature
            for creature in battlefield.creatures
            if movement_plan is not None
            and creature.creature_ref == movement_plan.creature_ref
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
        path_pen.setWidth(max(2, int(geometry.cell_size * 0.06)))
        painter.setPen(path_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(
                        geometry.origin_x + (path_x + 0.5) * geometry.cell_size,
                        geometry.origin_y + (path_y + 0.5) * geometry.cell_size,
                    )
                    for path_x, path_y in preview_cells
                ]
            )
        )
    return MovementPreview(planner, tuple(preview_cells))


def paint_area_overlay(
    painter: QPainter,
    geometry: BoardGeometry,
    overlay: Mapping[str, object] | None,
) -> None:
    """Paint an area template and its selected origin cell."""

    overlay_cells = area_overlay_cells(overlay)
    overlay_origin = area_overlay_origin(overlay)
    if overlay_cells:
        painter.setPen(Qt.PenStyle.NoPen)
        for cell_x, cell_y in overlay_cells:
            draw_x = geometry.origin_x + cell_x * geometry.cell_size
            draw_y = geometry.origin_y + cell_y * geometry.cell_size
            painter.fillRect(
                int(draw_x + 1),
                int(draw_y + 1),
                max(1, int(geometry.cell_size - 2)),
                max(1, int(geometry.cell_size - 2)),
                QColor(72, 142, 212, 95),
            )
        area = continuous_area(overlay)
        if area is not None:
            outline = continuous_area_outline(area)
            if outline is not None:
                painter.setBrush(QColor(132, 188, 234, 55))
                outline_pen = QPen(QColor("#1c4e80"), 2)
                outline_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(outline_pen)
                painter.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(
                                geometry.origin_x + point.x * geometry.cell_size,
                                geometry.origin_y + point.y * geometry.cell_size,
                            )
                            for point in outline
                        ]
                    )
                )
        painter.setPen(QPen(QColor("#2a5f92"), 2))
        for cell_x, cell_y in overlay_cells:
            draw_x = geometry.origin_x + cell_x * geometry.cell_size
            draw_y = geometry.origin_y + cell_y * geometry.cell_size
            painter.drawRect(
                int(draw_x + 1),
                int(draw_y + 1),
                max(1, int(geometry.cell_size - 2)),
                max(1, int(geometry.cell_size - 2)),
            )

    if overlay_origin is None:
        return
    origin_cell_x, origin_cell_y = overlay_origin
    draw_x = geometry.origin_x + origin_cell_x * geometry.cell_size
    draw_y = geometry.origin_y + origin_cell_y * geometry.cell_size
    painter.setBrush(QColor(255, 247, 186, 110))
    painter.setPen(QPen(QColor("#9a7a17"), 3))
    painter.drawRect(
        int(draw_x + 2),
        int(draw_y + 2),
        max(1, int(geometry.cell_size - 4)),
        max(1, int(geometry.cell_size - 4)),
    )


def paint_movement_destination(
    painter: QPainter,
    geometry: BoardGeometry,
    preview: MovementPreview,
    load_image: ImageLoader,
    token_colors: TokenColors,
) -> None:
    """Paint a translucent creature token at the path destination."""

    planner = preview.creature
    if planner is None or len(preview.cells) <= 1:
        return
    destination_x, destination_y = preview.cells[-1]
    center_x = geometry.origin_x + (destination_x + 0.5) * geometry.cell_size
    center_y = geometry.origin_y + (destination_y + 0.5) * geometry.cell_size
    token = load_image(planner.token_image)
    painter.setOpacity(0.45)
    if token is not None:
        maximum_size = geometry.cell_size * 0.98
        scale = min(maximum_size / token.width(), maximum_size / token.height())
        sprite_width = max(1, int(token.width() * scale))
        sprite_height = max(1, int(token.height() * scale))
        painter.drawPixmap(
            int(center_x - sprite_width / 2),
            int(center_y + geometry.cell_size / 2 - sprite_height),
            sprite_width,
            sprite_height,
            token,
        )
    else:
        radius = max(14, int(geometry.cell_size * 0.38))
        fill, border = token_colors(planner.team_color)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 2))
        painter.drawEllipse(
            int(center_x - radius),
            int(center_y - radius),
            radius * 2,
            radius * 2,
        )
    painter.setOpacity(1.0)
