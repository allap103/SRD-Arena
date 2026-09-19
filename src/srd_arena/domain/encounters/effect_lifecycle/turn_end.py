"""Expire ongoing effects tied to the end of a creature's turn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.runtime import UntilTurnEnd

from .removal import _remove_effect_tree

if TYPE_CHECKING:
    from ..encounter import EncounterState


def expire_ongoing_effects_for_turn_end(
    state: EncounterState,
    creature_ref: str,
) -> None:
    """Remove ongoing effects whose named turn-end boundary has arrived.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> effect = SimpleNamespace(duration=UntilTurnEnd("mage", 2))
    >>> state = SimpleNamespace(
    ...     ongoing_effects=[effect], round=SimpleNamespace(matches=lambda n: n == 2)
    ... )
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.turn_end."
    ...     "_remove_effect_tree"
    ... ) as remove:
    ...     expire_ongoing_effects_for_turn_end(state, "mage")
    >>> remove.call_args.args[1] is effect
    True
    """

    expired = tuple(
        effect
        for effect in state.ongoing_effects
        if isinstance(effect.duration, UntilTurnEnd)
        and effect.duration.creature_ref == creature_ref
        and (
            effect.duration.round_number is None
            or state.round.matches(effect.duration.round_number)
        )
    )
    for effect in expired:
        _remove_effect_tree(state, effect)
