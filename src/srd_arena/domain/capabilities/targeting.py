"""Target declarations for executable capabilities."""

from dataclasses import dataclass
from typing import Literal

from .requirements import CapabilityRequirement


@dataclass(frozen=True)
class TargetCount:
    """Represent a target count."""

    minimum: int = 1
    maximum: int | Literal["all", "ability_modifier"] = 1


@dataclass(frozen=True)
class CapabilityTarget:
    """Represent a capability target."""

    kind: Literal["self", "creature", "area"]
    count: TargetCount = TargetCount()
    range_feet: int | None = None
    shape: str | None = None
    size_feet: int | None = None
    width_feet: int | None = None
    origin: str = "self"
    line_of_sight: bool = False
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"
    excludes_source: bool = False
    requirements: tuple[CapabilityRequirement, ...] = ()
