"""Provide config support for the encounter package."""

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
class TargetSelectionMode:
    """Represent a target selection mode."""

    kind: str
    source_trigger_id: str | None = None
    variant_id: str | None = None


@dataclass(frozen=True)
class ActionMenuScope:
    """Represent an action menu scope."""

    economy: str
    bucket: str
