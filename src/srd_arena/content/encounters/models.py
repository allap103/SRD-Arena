"""Frontend-neutral metadata for selecting authored encounters."""

from dataclasses import dataclass

DEFAULT_GRID_COLOR = "#d3d3d3"


@dataclass(frozen=True)
class EncounterPresentation:
    """Optional visual metadata supplied to graphical driving adapters."""

    background_image: str | None = None
    grid_color: str = DEFAULT_GRID_COLOR
    grid_opacity: float = 1.0


@dataclass(frozen=True)
class EncounterSummary:
    """Encounter information suitable for selection by any driving adapter."""

    id: str
    label: str
    presentation: EncounterPresentation = EncounterPresentation()
