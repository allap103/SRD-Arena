"""Paint battlefield snapshots independently from widget interaction state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF

from srd_arena.domain.geometry import continuous_area_outline

from ...floating_labels import BATTLEFIELD_FLOATING_LABEL_STYLE
from ...presentation.models import BattlefieldCreatureView, BattlefieldView
from .area_previews import (
    area_overlay_label,
    continuous_area,
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
    status_tooltip_label_rect,
    target_allocation_badge_position,
)


@dataclass(frozen=True)
class BattlefieldRenderGeometry:
    """Describe the visible board rectangle in widget pixel coordinates."""

    viewport: QRect
    origin_x: float
    origin_y: float
    cell_size: float
    columns: int
    rows: int

    @property
    def board_width(self) -> float:
        """Return the rendered board width in pixels."""

        return self.cell_size * self.columns

    @property
    def board_height(self) -> float:
        """Return the rendered board height in pixels."""

        return self.cell_size * self.rows


@dataclass(frozen=True)
class BattlefieldRenderInput:
    """Snapshot presentation and transient overlays for one battlefield paint."""

    battlefield: BattlefieldView
    geometry: BattlefieldRenderGeometry
    area_overlay: Mapping[str, object] | None
    movement_plan: MovementPlan | None
    hover_cell: tuple[int, int] | None
    targetable_creature_refs: frozenset[str]
    selected_creature_ref: str | None
    target_allocation_counts: tuple[tuple[str, int], ...]
    targeting_label: str | None
    visible_status_tooltip: str | None
    status_tooltip_anchor: tuple[float, float] | None
    show_team_outlines: bool
    always_show_creature_names: bool
    viewport_width: int
    viewport_height: int


@dataclass(frozen=True)
class CreatureHitRegion:
    """Describe one painted creature token's circular pointer target."""

    creature_ref: str
    center_x: float
    center_y: float
    radius: float


@dataclass(frozen=True)
class BattlefieldRenderResult:
    """Return pointer regions produced by the completed paint pipeline."""

    creature_hits: tuple[CreatureHitRegion, ...]
    status_marker_hits: tuple[StatusMarkerHit, ...]


@dataclass(frozen=True)
class _MovementPreview:
    """Hold the moving creature and cells in its currently previewed path."""

    creature: BattlefieldCreatureView | None
    cells: tuple[tuple[int, int], ...]


def fallback_token_colors(team_color: str) -> tuple[QColor, QColor]:
    """Return valid fill and border colors for a token without an image.

    >>> fill, border = fallback_token_colors("not-a-color")
    >>> (fill.name(), border.isValid())
    ('#3f7fd5', True)
    """

    fill = QColor(team_color)
    if not fill.isValid():
        fill = QColor("#3f7fd5")
    return fill, fill.darker(180)


def floating_label_font() -> QFont:
    """Build the font shared by creature names and painted status tooltips."""

    style = BATTLEFIELD_FLOATING_LABEL_STYLE
    font = QFont()
    font.setWeight(QFont.Weight(style.font_weight))
    font.setPointSize(style.font_point_size)
    return font


class BattlefieldRenderer:
    """Own battlefield image caching and the complete ordered paint pipeline."""

    def __init__(self, *, image_root: Path | None = None) -> None:
        self._image_root = image_root
        self._image_cache: dict[str, QPixmap | None] = {}

    def paint(
        self,
        painter: QPainter,
        render_input: BattlefieldRenderInput,
    ) -> BattlefieldRenderResult:
        """Paint one immutable battlefield input and return its hit regions."""

        return _BattlefieldPaintSession(self, render_input).paint(painter)

    def _content_image(self, image_reference: str | None) -> QPixmap | None:
        """Load and cache one content image, or return None when unavailable."""

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


class _BattlefieldPaintSession:
    """Carry mutable hit-region output while painting one immutable input."""

    def __init__(
        self,
        renderer: BattlefieldRenderer,
        render_input: BattlefieldRenderInput,
    ) -> None:
        self._renderer = renderer
        self._input = render_input
        self._battlefield = render_input.battlefield
        self._show_team_outlines = render_input.show_team_outlines
        self._movement_plan = render_input.movement_plan
        self._hover_cell = render_input.hover_cell
        self._targetable_creature_refs = set(render_input.targetable_creature_refs)
        self._selected_creature_ref = render_input.selected_creature_ref
        self._target_allocation_counts = dict(render_input.target_allocation_counts)
        self._targeting_label = render_input.targeting_label
        self._visible_status_tooltip = render_input.visible_status_tooltip
        self._status_tooltip_anchor = render_input.status_tooltip_anchor
        self._always_show_creature_names = render_input.always_show_creature_names
        self._creature_positions: dict[str, tuple[float, float, float]] = {}
        self._status_marker_hits: list[StatusMarkerHit] = []

    def width(self) -> int:
        """Return the paint viewport width."""

        return self._input.viewport_width

    def height(self) -> int:
        """Return the paint viewport height."""

        return self._input.viewport_height

    def paint(self, painter: QPainter) -> BattlefieldRenderResult:
        """Run every battlefield paint phase in its established visual order."""

        geometry = self._input.geometry
        overlay = self._input.area_overlay
        self._paint_board(painter, geometry)
        self._paint_team_outlines(painter, geometry)
        movement_preview = self._paint_movement_plan(painter, geometry)
        self._paint_area_overlay(painter, geometry, overlay)
        self._paint_creatures(painter, geometry)
        self._paint_movement_destination(painter, geometry, movement_preview)
        self._paint_area_badge(painter, geometry, overlay)
        self._paint_targeting_badge(painter, geometry)
        self._paint_status_tooltip(painter)
        return BattlefieldRenderResult(
            creature_hits=tuple(
                CreatureHitRegion(creature_ref, center_x, center_y, radius)
                for creature_ref, (
                    center_x,
                    center_y,
                    radius,
                ) in self._creature_positions.items()
            ),
            status_marker_hits=tuple(self._status_marker_hits),
        )

    def _paint_board(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
    ) -> None:
        """Paint the board background and square grid."""

        assert self._battlefield is not None
        background = self._content_image(self._battlefield.background_image)
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

        grid_color = QColor(self._battlefield.grid_color)
        if not grid_color.isValid():
            grid_color = QColor("#d3d3d3")
        grid_color.setAlphaF(min(max(self._battlefield.grid_opacity, 0.0), 1.0))
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

    def _paint_team_outlines(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
    ) -> None:
        """Paint team-colored outlines around occupied cells when enabled."""

        if not self._show_team_outlines:
            return
        assert self._battlefield is not None
        for creature in self._battlefield.creatures:
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

    def _paint_movement_plan(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
    ) -> _MovementPreview:
        """Paint reachable cells and the currently hovered movement path."""

        assert self._battlefield is not None
        movement_paths = self._movement_plan.paths if self._movement_plan else {}
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
        return _MovementPreview(planner, tuple(preview_cells))

    @staticmethod
    def _paint_area_overlay(
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
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
            continuous = continuous_area(overlay)
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

    def _paint_creatures(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
    ) -> None:
        """Paint every creature and rebuild its pointer-interaction geometry."""

        assert self._battlefield is not None
        self._creature_positions = {}
        self._status_marker_hits = []
        for creature in self._battlefield.creatures:
            self._paint_creature(painter, geometry, creature)

    def _paint_creature(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
        creature: BattlefieldCreatureView,
    ) -> None:
        """Paint one creature's emphasis, token, labels, and status markers."""

        center_x = geometry.origin_x + (creature.position.x + 0.5) * geometry.cell_size
        center_y = geometry.origin_y + (creature.position.y + 0.5) * geometry.cell_size
        radius = max(14, int(geometry.cell_size * 0.38))
        self._creature_positions[creature.creature_ref] = (
            center_x,
            center_y,
            radius,
        )
        self._paint_creature_emphasis(
            painter,
            creature,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
        )
        self._paint_creature_token(
            painter,
            creature,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            cell_size=geometry.cell_size,
        )
        self._paint_target_allocation_badge(
            painter,
            creature,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            cell_size=geometry.cell_size,
        )
        self._paint_creature_name(
            painter,
            creature,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            cell_size=geometry.cell_size,
        )
        self._paint_status_markers(
            painter,
            creature,
            cell_x=geometry.origin_x + creature.position.x * geometry.cell_size,
            cell_y=geometry.origin_y + creature.position.y * geometry.cell_size,
            center_x=center_x,
            center_y=center_y,
            token_radius=radius,
            cell_size=geometry.cell_size,
        )

    def _paint_creature_emphasis(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
        *,
        center_x: float,
        center_y: float,
        radius: int,
    ) -> None:
        """Paint active, targetable, and selected emphasis behind a token."""

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

    def _paint_creature_token(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
        *,
        center_x: float,
        center_y: float,
        radius: int,
        cell_size: float,
    ) -> None:
        """Paint a creature image or its colored initial fallback token."""

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
            return

        fill, border = self._fallback_token_colors(creature.team_color)
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

    def _paint_target_allocation_badge(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
        *,
        center_x: float,
        center_y: float,
        radius: int,
        cell_size: float,
    ) -> None:
        """Paint how many repeated targets are allocated to a creature."""

        allocation_count = self._target_allocation_counts.get(
            creature.creature_ref,
            0,
        )
        if not allocation_count:
            return
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

    def _paint_creature_name(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
        *,
        center_x: float,
        center_y: float,
        radius: int,
        cell_size: float,
    ) -> None:
        """Paint a creature's floating name when configured or hovered."""

        if not (
            self._always_show_creature_names
            or self._hover_cell == (creature.position.x, creature.position.y)
        ):
            return
        label_style = BATTLEFIELD_FLOATING_LABEL_STYLE
        painter.setFont(self._floating_label_font())
        label_rect = creature_name_label_rect(
            center_x=center_x,
            center_y=center_y,
            token_radius=radius,
            cell_size=cell_size,
            text_width=painter.fontMetrics().horizontalAdvance(creature.name),
            text_height=painter.fontMetrics().height(),
            horizontal_padding=label_style.horizontal_padding,
            vertical_padding=label_style.vertical_padding,
            viewport_width=self.width(),
            viewport_height=self.height(),
        )
        self._paint_floating_label(
            painter,
            creature.name,
            rect=label_rect,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

    def _paint_movement_destination(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
        preview: _MovementPreview,
    ) -> None:
        """Paint a translucent creature token at the path destination."""

        planner = preview.creature
        if planner is None or len(preview.cells) <= 1:
            return
        destination_x, destination_y = preview.cells[-1]
        center_x = geometry.origin_x + (destination_x + 0.5) * geometry.cell_size
        center_y = geometry.origin_y + (destination_y + 0.5) * geometry.cell_size
        token = self._token_image(planner.token_image)
        painter.setOpacity(0.45)
        if token is not None:
            maximum_size = geometry.cell_size * 0.98
            scale = min(
                maximum_size / token.width(),
                maximum_size / token.height(),
            )
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

    @staticmethod
    def _paint_area_badge(
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
        overlay: Mapping[str, object] | None,
    ) -> None:
        """Paint the label describing an active area template."""

        if overlay is None:
            return
        badge_rect = geometry.viewport.adjusted(12, 12, -12, -12)
        badge_height = 32
        badge_width = min(
            int(geometry.cell_size * 3.8),
            max(160, badge_rect.width() // 3),
        )
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
            area_overlay_label(overlay),
        )

    def _paint_targeting_badge(
        self,
        painter: QPainter,
        geometry: BattlefieldRenderGeometry,
    ) -> None:
        """Paint the instructions for the active target-selection interaction."""

        if self._targeting_label is None:
            return
        badge_rect = geometry.viewport.adjusted(12, 12, -12, -12)
        badge_height = 34
        badge_width = min(
            max(260, int(geometry.cell_size * 6.5)),
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

    @staticmethod
    def _floating_label_font() -> QFont:
        return floating_label_font()

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

    @staticmethod
    def _fallback_token_colors(team_color: str) -> tuple[QColor, QColor]:
        return fallback_token_colors(team_color)

    def _token_image(self, image_reference: str | None) -> QPixmap | None:
        return self._renderer._content_image(image_reference)

    def _content_image(self, image_reference: str | None) -> QPixmap | None:
        return self._renderer._content_image(image_reference)
