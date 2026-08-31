"""Discover and load authored encounters by stable content identifier."""

from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.paths import (
    ENCOUNTERS_ROOT,
    IMAGES_ROOT,
    SYSTEM_CONTENT_ROOT,
)
from srd_arena.domain.encounters import EncounterDefinition

from .directory_loader import load_encounter_directory
from .discovery import discover_encounters
from .models import EncounterPresentation, EncounterSummary


@dataclass(frozen=True)
class EncounterCatalog:
    """List and load encounters from configured authored-content directories."""

    encounter_root: Path = ENCOUNTERS_ROOT
    system_directory: Path = SYSTEM_CONTENT_ROOT
    image_root: Path = IMAGES_ROOT

    def available_encounters(self) -> tuple[EncounterSummary, ...]:
        """Return validated summaries without loading full encounter content."""

        return tuple(
            EncounterSummary(
                id=source.id,
                label=source.schema.display_name,
                presentation=EncounterPresentation(
                    background_image=source.schema.background_image,
                    grid_color=source.schema.grid_color,
                    grid_opacity=source.schema.grid_opacity,
                ),
            )
            for source in discover_encounters(self.encounter_root)
        )

    def load_encounter(self, encounter_id: str) -> EncounterDefinition:
        """Build the encounter selected by its advertised stable ID."""

        source = next(
            (
                candidate
                for candidate in discover_encounters(self.encounter_root)
                if candidate.id == encounter_id
            ),
            None,
        )
        if source is None:
            raise KeyError(f"Unknown encounter '{encounter_id}'.")
        return load_encounter_directory(
            source.directory,
            system_directory=self.system_directory,
        )
