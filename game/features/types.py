from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

DiceRoller = Callable[[int, int], int]


@dataclass(frozen=True)
class FeatureActionResult:
    feature_id: str
    feature_name: str
    messages: list[tuple[str, str]]
    target_ref: str = "player"
    target_label: str = ""
    healing: int = 0
    roll_detail: dict[str, int | str] = field(default_factory=dict)
    uses_remaining: int = 0
