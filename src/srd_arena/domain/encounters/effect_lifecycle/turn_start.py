"""Apply ongoing-effect expiry and grants at the start of a turn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.runtime import OngoingEffect, Rounds

from .removal import _remove_effect_tree

if TYPE_CHECKING:
    from ..encounter import EncounterState


def expire_ongoing_effects_for_turn_start(
    state: EncounterState,
    creature_ref: str,
) -> None:
    """Expire source durations and grant target turn-start temporary HP.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock
    >>> source = SimpleNamespace(applied_by_ref="cleric")
    >>> effect = SimpleNamespace(
    ...     identity=SimpleNamespace(source=source),
    ...     target_refs=("hero",),
    ...     lifecycle=SimpleNamespace(turn_start_temporary_hit_points=5),
    ...     duration=SimpleNamespace(),
    ... )
    >>> creature = Mock()
    >>> state = SimpleNamespace(
    ...     ongoing_effects=[effect], round=SimpleNamespace(number=1),
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ... )
    >>> expire_ongoing_effects_for_turn_start(state, "hero")
    >>> creature.grant_temporary_hit_points.call_args.args
    (5,)
    """

    expired = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.applied_by_ref == creature_ref
        and _round_duration_expired(state, effect)
    )
    for effect in expired:
        _remove_effect_tree(state, effect)
    for effect in tuple(state.ongoing_effects):
        if creature_ref not in effect.target_refs:
            continue
        temporary_hit_points = effect.lifecycle.turn_start_temporary_hit_points
        if temporary_hit_points > 0:
            state.creatures[creature_ref].creature.grant_temporary_hit_points(
                temporary_hit_points
            )


def _round_duration_expired(
    state: EncounterState,
    effect: OngoingEffect,
) -> bool:
    started_round = effect.lifecycle.started_round
    return (
        isinstance(effect.duration, Rounds)
        and isinstance(started_round, int)
        and state.round.number >= started_round + effect.duration.count
    )
