"""Build complete domain encounters from authored content directories."""

from __future__ import annotations

from pathlib import Path

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
    load_subclass_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.common.sources import load_json
from srd_arena.content.creatures import (
    load_bestiary_catalog,
    load_player_character_templates,
)
from srd_arena.content.equipment import load_system_items
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.geometry import GeometryConfig

from .loader import load_encounter_file
from .schema import EncounterConfigSchema


def load_encounter_directory(
    encounter_directory: str | Path,
    *,
    system_directory: str | Path = SYSTEM_CONTENT_ROOT,
) -> EncounterDefinition:
    """Validate one encounter directory and build its complete definition."""

    directory = Path(encounter_directory)
    system_path = Path(system_directory)
    config = _load_config(directory / "config.json")
    loaded = load_encounter_file(
        directory / "encounter.json",
        load_bestiary_catalog(system_path),
        load_class_catalog(system_path),
        load_player_character_templates(directory / "player_characters"),
        load_optional_feature_catalog(system_path),
        load_subclass_catalog(system_path),
        load_spell_catalog(system_path),
    )
    definition = loaded.definition
    definition.display_name = config.display_name
    definition.creatures = loaded.creatures
    definition.items = tuple(load_system_items(system_path))
    definition.geometry_config = GeometryConfig(
        directional_area_cell_coverage_threshold=(
            config.geometry.directional_area_cell_coverage_threshold
        )
    )
    return definition


def _load_config(path: Path) -> EncounterConfigSchema:
    """Read and validate encounter configuration with documented defaults."""

    if not path.exists():
        return EncounterConfigSchema()
    return EncounterConfigSchema.model_validate(load_json(path))
