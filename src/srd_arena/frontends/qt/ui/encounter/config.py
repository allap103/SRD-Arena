from __future__ import annotations

from dataclasses import dataclass

ENCOUNTER_BUTTON_HEIGHT = 36
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
    kind: str
    source_trigger_id: str | None = None


@dataclass(frozen=True)
class ActionMenuScope:
    economy: str
    bucket: str
