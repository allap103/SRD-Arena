"""Paint battlefield creatures and return their pointer interaction regions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap

from ...floating_labels import BATTLEFIELD_FLOATING_LABEL_STYLE
from ...presentation.models import BattlefieldCreatureView, BattlefieldView
from .battlefield_overlay_painter import (
    floating_label_font,
    paint_floating_label,
)
from .config import BattlefieldRenderGeometry
from .status_markers import (
    StatusMarkerHit,
    build_status_marker_specs,
    creature_name_label_rect,
    status_marker_hit_radius,
    status_marker_positions,
    target_allocation_badge_position,
)

ImageLoader = Callable[[str | None], QPixmap | None]
TokenColors = Callable[[str], tuple[QColor, QColor]]
CreaturePosition = tuple[str, float, float, float]


@dataclass(frozen=True)
class CreaturePaintInput:
    """Contain the read-only creature-specific state for one paint."""

    battlefield: BattlefieldView
    geometry: BattlefieldRenderGeometry
    hover_cell: tuple[int, int] | None
    targetable_creature_refs: frozenset[str]
    selected_creature_ref: str | None
    target_allocation_counts: tuple[tuple[str, int], ...]
    always_show_creature_names: bool
    viewport_width: int
    viewport_height: int


@dataclass(frozen=True)
class CreaturePaintResult:
    """Return token positions and status-marker hits from creature painting."""

    positions: tuple[CreaturePosition, ...]
    status_marker_hits: tuple[StatusMarkerHit, ...]


class CreaturePainter:
    """Paint creature visuals while collecting their generated hit geometry."""

    def __init__(
        self,
        paint_input: CreaturePaintInput,
        load_image: ImageLoader,
        token_colors: TokenColors,
    ) -> None:
        self._input = paint_input
        self._load_image = load_image
        self._token_colors = token_colors
        self._positions: list[CreaturePosition] = []
        self._status_marker_hits: list[StatusMarkerHit] = []
        self._allocation_counts = dict(paint_input.target_allocation_counts)

    def paint(self, painter: QPainter) -> CreaturePaintResult:
        """Paint every creature and return the generated interaction regions."""

        for creature in self._input.battlefield.creatures:
            self._paint_creature(painter, creature)
        return CreaturePaintResult(
            positions=tuple(self._positions),
            status_marker_hits=tuple(self._status_marker_hits),
        )

    def _paint_creature(
        self,
        painter: QPainter,
        creature: BattlefieldCreatureView,
    ) -> None:
        """Paint one creature's emphasis, token, labels, and status markers."""

        geometry = self._input.geometry
        center_x = geometry.origin_x + (creature.position.x + 0.5) * geometry.cell_size
        center_y = geometry.origin_y + (creature.position.y + 0.5) * geometry.cell_size
        radius = max(14, int(geometry.cell_size * 0.38))
        self._positions.append((creature.creature_ref, center_x, center_y, radius))
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

        if creature.creature_ref in self._input.targetable_creature_refs:
            painter.setBrush(QColor(84, 196, 110, 70))
            painter.setPen(QPen(QColor("#2d7a3d"), 2))
            target_radius = int(radius * 1.3)
            painter.drawEllipse(
                int(center_x - target_radius),
                int(center_y - target_radius),
                target_radius * 2,
                target_radius * 2,
            )

        if creature.creature_ref == self._input.selected_creature_ref:
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

        token = self._load_image(creature.token_image)
        if token is not None:
            maximum_size = cell_size * 0.98
            scale = min(maximum_size / token.width(), maximum_size / token.height())
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

        fill, border = self._token_colors(creature.team_color)
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

        allocation_count = self._allocation_counts.get(creature.creature_ref, 0)
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
            self._input.always_show_creature_names
            or self._input.hover_cell == (creature.position.x, creature.position.y)
        ):
            return
        label_style = BATTLEFIELD_FLOATING_LABEL_STYLE
        painter.setFont(floating_label_font())
        label_rect = creature_name_label_rect(
            center_x=center_x,
            center_y=center_y,
            token_radius=radius,
            cell_size=cell_size,
            text_width=painter.fontMetrics().horizontalAdvance(creature.name),
            text_height=painter.fontMetrics().height(),
            horizontal_padding=label_style.horizontal_padding,
            vertical_padding=label_style.vertical_padding,
            viewport_width=self._input.viewport_width,
            viewport_height=self._input.viewport_height,
        )
        paint_floating_label(
            painter,
            creature.name,
            rect=label_rect,
            alignment=Qt.AlignmentFlag.AlignCenter,
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
