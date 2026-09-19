"""Resolve and consume one-use roll adjustments from ongoing effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..rule_queries.models import RollRuleResult
from .removal import _remove_effect_target

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_saving_throw_modifier(
    state: EncounterState,
    creature_ref: str,
    rules: RollRuleResult,
) -> int:
    """Roll sourced save modifiers and consume providers marked for one use.

    Persistent modifiers remain active. A consumed multi-target effect is
    detached only from the creature whose saving throw used it.
    """

    value = rules.resolve_modifier(state.dice.roll_die)
    consumed_provider_ids = {
        contribution.provider_state_id
        for contribution in rules.contributions
        if contribution.modifier.consume_on_use
    }
    for effect in tuple(state.ongoing_effects):
        if (
            effect.identity.id in consumed_provider_ids
            and creature_ref in effect.target_refs
        ):
            _remove_effect_target(state, effect, creature_ref)
    return value
