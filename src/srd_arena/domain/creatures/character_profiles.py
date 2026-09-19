"""Record the authored selections that identify a fixed character build."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterOptionRef:
    """Identify selected character content without embedding its rule meaning."""

    name: str
    source: str | None = None


@dataclass(frozen=True)
class CharacterProfile:
    """Retain the selections from which one canonical creature was compiled.

    Feature implementations may inspect this identity through focused rule
    providers, while controllers remain independent of the selected build.
    """

    build_id: str
    species: CharacterOptionRef
    background: CharacterOptionRef
    subclass: CharacterOptionRef | None = None
    feats: tuple[CharacterOptionRef, ...] = ()
    selected_features: tuple[CharacterOptionRef, ...] = ()
    weapon_masteries: tuple[str, ...] = ()
