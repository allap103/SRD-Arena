"""Build domain scenarios from authored encounters and supporting content."""

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
from srd_arena.content.encounters import load_encounter
from srd_arena.content.equipment import load_system_items
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.geometry import GeometryConfig
from srd_arena.domain.scenarios import ScenarioDefinition

from .schema import ScenarioSchema


def load_scenario_directory(
    scenario_directory: str | Path,
    *,
    start_encounter_id: str | None = None,
    system_directory: str | Path = SYSTEM_CONTENT_ROOT,
) -> ScenarioDefinition:
    """Validate one scenario directory and build its domain definition.

    The explicit path entry point supports tests and other callers that already
    own a content directory. Interactive clients select IDs through
    :class:`~srd_arena.content.scenarios.ScenarioCatalog` instead.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory)
    ...     _ = (path / "config.json").write_text(
    ...         '{"display_name": "Empty", "encounters": ["missing"]}')
    ...     (path / "encounters").mkdir()
    ...     try:
    ...         load_scenario_directory(path)
    ...     except ValueError as error:
    ...         "missing encounters" in str(error)
    True
    """

    directory = Path(scenario_directory)
    system_path = Path(system_directory)
    config = _load_config(directory / "config.json")
    bestiary = load_bestiary_catalog(system_path)
    classes = load_class_catalog(system_path)
    subclasses = load_subclass_catalog(system_path)
    spells = load_spell_catalog(system_path)
    optional_features = load_optional_feature_catalog(system_path)
    player_characters = load_player_character_templates(directory / "player_characters")
    loaded_encounters = [
        load_encounter(
            path,
            bestiary,
            classes,
            player_characters,
            optional_features,
            subclasses,
            spells,
        )
        for path in (directory / "encounters").glob("*")
    ]
    encounters = {
        encounter.definition.id: encounter.definition for encounter in loaded_encounters
    }
    creatures_by_id = {
        creature.id: creature
        for encounter in loaded_encounters
        for creature in encounter.creatures
    }
    _link_encounters(encounters, config.encounters)
    start = start_encounter_id or config.encounters[0]
    return ScenarioDefinition(
        id=directory.name,
        display_name=config.display_name,
        encounters=encounters,
        encounter_order=config.encounters,
        start_encounter_id=start,
        creatures=tuple(creatures_by_id.values()),
        items=tuple(load_system_items(system_path)),
        geometry_config=GeometryConfig(
            directional_area_cell_coverage_threshold=(
                config.geometry.directional_area_cell_coverage_threshold
            )
        ),
    )


def _link_encounters(
    encounters: dict[str, EncounterDefinition],
    encounter_order: tuple[str, ...],
) -> None:
    """Validate encounter order and install its victory/defeat transitions."""

    missing = tuple(
        encounter_id
        for encounter_id in encounter_order
        if encounter_id not in encounters
    )
    if missing:
        raise ValueError(
            "Scenario references missing encounters: " + ", ".join(missing)
        )
    for index, encounter_id in enumerate(encounter_order):
        next_encounter_id = (
            encounter_order[index + 1]
            if index + 1 < len(encounter_order)
            else encounter_id
        )
        encounter = encounters[encounter_id]
        if encounter.victory is None or encounter.defeat is None:
            raise ValueError(f"Encounter '{encounter_id}' must define transitions.")
        encounter.victory.next_encounter_id = next_encounter_id
        encounter.defeat.next_encounter_id = encounter_id


def _load_config(path: Path) -> ScenarioSchema:
    """Read and validate scenario configuration with documented defaults."""

    if not path.exists():
        return ScenarioSchema()
    return ScenarioSchema.model_validate(load_json(path))
