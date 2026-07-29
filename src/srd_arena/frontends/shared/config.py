from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GRID_COLOR = "#d3d3d3"


@dataclass(frozen=True)
class EncounterPresentationConfig:
    background_image: str | None = None
    grid_color: str = DEFAULT_GRID_COLOR
    grid_opacity: float = 1.0


def load_encounter_presentation_config(
    scenario_directory: str | Path,
) -> EncounterPresentationConfig:
    config_path = Path(scenario_directory) / "config.json"
    if not config_path.exists():
        return EncounterPresentationConfig()

    with config_path.open("r", encoding="utf-8") as config_file:
        payload = json.load(config_file)

    configured_opacity = payload.get("grid_opacity", 1.0)
    grid_opacity = (
        min(max(float(configured_opacity), 0.0), 1.0)
        if isinstance(configured_opacity, (int, float))
        else 1.0
    )
    background_image = payload.get("background_image")
    grid_color = payload.get("grid_color")
    return EncounterPresentationConfig(
        background_image=(
            background_image
            if isinstance(background_image, str) and background_image
            else None
        ),
        grid_color=(
            grid_color
            if isinstance(grid_color, str) and grid_color
            else DEFAULT_GRID_COLOR
        ),
        grid_opacity=grid_opacity,
    )
