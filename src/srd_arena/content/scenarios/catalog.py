"""Discover and load authored scenarios by stable content identifier."""

from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.paths import (
    IMAGES_ROOT,
    SCENARIOS_ROOT,
    SYSTEM_CONTENT_ROOT,
)
from srd_arena.domain.scenarios import ScenarioDefinition

from .discovery import discover_scenarios
from .loader import load_scenario_directory
from .models import ScenarioPresentation, ScenarioSummary


@dataclass(frozen=True)
class ScenarioCatalog:
    """List and load scenarios from configured authored-content directories."""

    scenario_root: Path = SCENARIOS_ROOT
    system_directory: Path = SYSTEM_CONTENT_ROOT
    image_root: Path = IMAGES_ROOT

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        """Return validated scenario summaries without loading encounters.

        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as temporary_directory:
        ...     root = Path(temporary_directory)
        ...     scenario = root / "demo"
        ...     (scenario / "encounters").mkdir(parents=True)
        ...     _ = (scenario / "config.json").write_text(
        ...         '{"display_name": "Demo"}', encoding="utf-8")
        ...     summaries = ScenarioCatalog(scenario_root=root).available_scenarios()
        >>> [(summary.id, summary.label) for summary in summaries]
        [('demo', 'Demo')]
        """

        return tuple(
            ScenarioSummary(
                id=source.id,
                label=source.schema.display_name,
                presentation=ScenarioPresentation(
                    background_image=source.schema.background_image,
                    grid_color=source.schema.grid_color,
                    grid_opacity=source.schema.grid_opacity,
                ),
            )
            for source in discover_scenarios(self.scenario_root)
        )

    def load_scenario(self, scenario_id: str) -> ScenarioDefinition:
        """Build a domain scenario selected by its advertised stable ID.

        Unknown IDs fail before any system content is loaded.

        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as temporary_directory:
        ...     catalog = ScenarioCatalog(scenario_root=Path(temporary_directory))
        ...     try:
        ...         catalog.load_scenario("missing")
        ...     except KeyError as error:
        ...         "Unknown scenario 'missing'." in str(error)
        True
        """

        source = next(
            (
                candidate
                for candidate in discover_scenarios(self.scenario_root)
                if candidate.id == scenario_id
            ),
            None,
        )
        if source is None:
            raise KeyError(f"Unknown scenario '{scenario_id}'.")
        return load_scenario_directory(
            source.directory,
            system_directory=self.system_directory,
        )
