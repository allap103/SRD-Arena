from __future__ import annotations

from dataclasses import dataclass


DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD = 0.5


@dataclass(frozen=True)
class RulesConfig:
    directional_aoe_cell_coverage_threshold: float = (
        DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD
    )
