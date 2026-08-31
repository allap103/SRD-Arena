"""Describe the hand-held items authored for a creature."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Equipment:
    """Record the immutable hand loadout selected by authored content.

    Changing equipment during an encounter is outside the current project scope.

    >>> Equipment(right_hand="longsword").right_hand
    'longsword'
    """

    right_hand: str | None = None
    left_hand: str | None = None
