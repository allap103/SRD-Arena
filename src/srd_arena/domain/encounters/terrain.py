"""Typed ground terrain authored as cells in an encounter definition."""

from dataclasses import dataclass
from enum import StrEnum

from srd_arena.domain.geometry import Position


class TerrainTraversal(StrEnum):
    """Describe how a creature may enter a terrain cell."""

    NORMAL = "normal"
    DIFFICULT = "difficult"
    BLOCKED = "blocked"


class CoverDegree(StrEnum):
    """Enumerate the SRD degrees of cover in increasing protection order."""

    NONE = "none"
    HALF = "half"
    THREE_QUARTERS = "three_quarters"
    TOTAL = "total"

    @property
    def rank(self) -> int:
        """Return an ordering value used to select the most protective cover."""

        return {
            CoverDegree.NONE: 0,
            CoverDegree.HALF: 1,
            CoverDegree.THREE_QUARTERS: 2,
            CoverDegree.TOTAL: 3,
        }[self]

    @property
    def bonus(self) -> int:
        """Return the Armor Class and Dexterity-save bonus granted by cover."""

        return {
            CoverDegree.NONE: 0,
            CoverDegree.HALF: 2,
            CoverDegree.THREE_QUARTERS: 5,
            CoverDegree.TOTAL: 0,
        }[self]


@dataclass(frozen=True)
class TerrainCell:
    """Describe traversal and cover supplied by one battlefield cell."""

    position: Position
    traversal: TerrainTraversal = TerrainTraversal.NORMAL
    cover: CoverDegree = CoverDegree.NONE
