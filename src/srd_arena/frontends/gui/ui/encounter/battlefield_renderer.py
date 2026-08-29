"""Paint battlefield snapshots independently from widget interaction state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from PySide6.QtGui import QColor, QPainter, QPixmap

from ...presentation.models import BattlefieldView
from .battlefield_board_painter import (
    paint_area_overlay,
    paint_board,
    paint_movement_destination,
    paint_movement_plan,
    paint_team_outlines,
)
from .battlefield_creature_painter import CreaturePainter, CreaturePaintInput
from .battlefield_overlay_painter import (
    floating_label_font,
    paint_area_badge,
    paint_status_tooltip,
    paint_targeting_badge,
)
from .config import BattlefieldRenderGeometry
from .movement import MovementPlan
from .status_markers import StatusMarkerHit

__all__ = [
    "BattlefieldRenderInput",
    "BattlefieldRenderResult",
    "BattlefieldRenderer",
    "CreatureHitRegion",
    "fallback_token_colors",
    "floating_label_font",
]


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

    def __post_init__(self) -> None:
        """Detach nested area data from mutable targeting-widget storage."""

        if self.area_overlay is None:
            return
        frozen_overlay = _freeze_render_value(self.area_overlay)
        object.__setattr__(
            self,
            "area_overlay",
            cast(Mapping[str, object], frozen_overlay),
        )


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


def _freeze_render_value(value: object) -> object:
    """Recursively copy transient overlay collections into read-only values."""

    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        frozen: dict[str, object] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("Battlefield overlay keys must be strings.")
            frozen[key] = _freeze_render_value(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_render_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_render_value(item) for item in value)
    return value


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

        geometry = render_input.geometry
        battlefield = render_input.battlefield
        overlay = render_input.area_overlay
        paint_board(painter, battlefield, geometry, self._content_image)
        paint_team_outlines(
            painter,
            battlefield,
            geometry,
            visible=render_input.show_team_outlines,
        )
        movement_preview = paint_movement_plan(
            painter,
            battlefield,
            geometry,
            render_input.movement_plan,
            render_input.hover_cell,
        )
        paint_area_overlay(painter, geometry, overlay)
        creatures = CreaturePainter(
            CreaturePaintInput(
                battlefield=battlefield,
                geometry=geometry,
                hover_cell=render_input.hover_cell,
                targetable_creature_refs=render_input.targetable_creature_refs,
                selected_creature_ref=render_input.selected_creature_ref,
                target_allocation_counts=render_input.target_allocation_counts,
                always_show_creature_names=render_input.always_show_creature_names,
                viewport_width=render_input.viewport_width,
                viewport_height=render_input.viewport_height,
            ),
            self._content_image,
            fallback_token_colors,
        ).paint(painter)
        paint_movement_destination(
            painter,
            geometry,
            movement_preview,
            self._content_image,
            fallback_token_colors,
        )
        paint_area_badge(painter, geometry, overlay)
        paint_targeting_badge(painter, geometry, render_input.targeting_label)
        paint_status_tooltip(
            painter,
            render_input.visible_status_tooltip,
            render_input.status_tooltip_anchor,
            viewport_width=render_input.viewport_width,
            viewport_height=render_input.viewport_height,
        )
        return BattlefieldRenderResult(
            creature_hits=tuple(
                CreatureHitRegion(creature_ref, center_x, center_y, radius)
                for creature_ref, center_x, center_y, radius in creatures.positions
            ),
            status_marker_hits=creatures.status_marker_hits,
        )

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
