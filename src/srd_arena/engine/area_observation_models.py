"""Public geometric parameters and potential creature coverage for aimed actions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConeTemplateObservation:
    """A cone's public dimensions and the encounter's rasterization policy."""

    length_squares: int
    coverage_threshold: float


@dataclass(frozen=True)
class AreaAimObservation:
    """One representative aim and its currently disclosed living footprints.

    Membership predicts geometric coverage, not successful saves, damage,
    private target eligibility or the absence of hidden creatures.
    """

    aim: tuple[float, float]
    creature_refs: tuple[str, ...]
