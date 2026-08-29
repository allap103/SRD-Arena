"""Define GUI-only layout constants and transient interaction state."""

from __future__ import annotations

from dataclasses import dataclass

ENCOUNTER_BUTTON_HEIGHT = 32
RESOURCE_BAR_HEIGHT = 28
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


@dataclass(frozen=True)
class BattlefieldRenderGeometry:
    """Describe the visible board rectangle in widget pixel coordinates."""

    viewport: tuple[int, int, int, int]
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
class TargetSelectionMode:
    """Track which staged targeting interaction battlefield clicks configure."""

    kind: str
    source_trigger_id: str | None = None
    variant_id: str | None = None


@dataclass(frozen=True)
class ActionMenuScope:
    """Identify an action-economy section and its expandable menu bucket."""

    economy: str
    bucket: str
