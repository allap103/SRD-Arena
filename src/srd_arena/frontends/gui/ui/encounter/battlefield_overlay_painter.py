"""Paint battlefield badges, floating labels, and status tooltips."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from ...floating_labels import BATTLEFIELD_FLOATING_LABEL_STYLE
from .area_previews import area_overlay_label
from .config import BattlefieldRenderGeometry
from .status_markers import status_tooltip_label_rect


def floating_label_font() -> QFont:
    """Build the font shared by creature names and painted status tooltips."""

    style = BATTLEFIELD_FLOATING_LABEL_STYLE
    font = QFont()
    font.setWeight(QFont.Weight(style.font_weight))
    font.setPointSize(style.font_point_size)
    return font


def paint_floating_label(
    painter: QPainter,
    text: str,
    *,
    rect: tuple[float, float, float, float],
    alignment: Qt.AlignmentFlag,
) -> None:
    """Paint text with the shared floating battlefield-label style."""

    style = BATTLEFIELD_FLOATING_LABEL_STYLE
    label_x, label_y, label_width, label_height = rect
    painter.save()
    painter.setFont(floating_label_font())
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


def paint_area_badge(
    painter: QPainter,
    geometry: BattlefieldRenderGeometry,
    overlay: Mapping[str, object] | None,
) -> None:
    """Paint the label describing an active area template."""

    if overlay is None:
        return
    viewport_x, viewport_y, viewport_width, _ = geometry.viewport
    badge_x = viewport_x + 12
    badge_y = viewport_y + 12
    available_width = max(0, viewport_width - 24)
    badge_height = 32
    badge_width = min(
        int(geometry.cell_size * 3.8),
        max(160, available_width // 3),
    )
    painter.setBrush(QColor(23, 54, 74, 220))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(
        badge_x,
        badge_y,
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
        badge_x + 12,
        badge_y,
        badge_width - 24,
        badge_height,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        area_overlay_label(overlay),
    )


def paint_targeting_badge(
    painter: QPainter,
    geometry: BattlefieldRenderGeometry,
    targeting_label: str | None,
) -> None:
    """Paint instructions for the active target-selection interaction."""

    if targeting_label is None:
        return
    viewport_x, viewport_y, viewport_width, _ = geometry.viewport
    badge_x = viewport_x + 12
    badge_y = viewport_y + 12
    available_width = max(0, viewport_width - 24)
    badge_height = 34
    badge_width = min(
        max(260, int(geometry.cell_size * 6.5)),
        available_width,
    )
    painter.setBrush(QColor(37, 30, 14, 225))
    painter.setPen(QPen(QColor("#d4ad45"), 2))
    painter.drawRoundedRect(
        badge_x,
        badge_y,
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
        badge_x + 12,
        badge_y,
        badge_width - 24,
        badge_height,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        targeting_label,
    )


def paint_status_tooltip(
    painter: QPainter,
    text: str | None,
    anchor: tuple[float, float] | None,
    *,
    viewport_width: int,
    viewport_height: int,
) -> None:
    """Paint a status tooltip anchored at its hovered marker."""

    if text is None or anchor is None:
        return
    style = BATTLEFIELD_FLOATING_LABEL_STYLE
    painter.setFont(floating_label_font())
    metrics = painter.fontMetrics()
    lines = text.splitlines() or [""]
    label_rect = status_tooltip_label_rect(
        anchor_x=anchor[0],
        anchor_y=anchor[1],
        text_width=max(metrics.horizontalAdvance(line) for line in lines),
        text_height=metrics.height() * len(lines),
        horizontal_padding=style.horizontal_padding,
        vertical_padding=style.vertical_padding,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )
    paint_floating_label(
        painter,
        text,
        rect=label_rect,
        alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
