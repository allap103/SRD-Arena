"""Public geometric parameters and potential creature coverage for aimed actions."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AreaTemplateObservation:
    """Public area geometry; size is radius for radius areas, length otherwise."""

    shape: Literal["cone", "line", "cube", "radius"]
    placement: Literal["point", "directional"]
    size_squares: int
    width_squares: float | None = None
    coverage_threshold: float | None = None


@dataclass(frozen=True)
class AreaAimObservation:
    """One integer aim and its currently disclosed living footprints.

    Membership predicts geometric coverage, not successful saves, damage,
    private target eligibility or the absence of hidden creatures.
    """

    aim: tuple[float, float]
    creature_refs: tuple[str, ...]
