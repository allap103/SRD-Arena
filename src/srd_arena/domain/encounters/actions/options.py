"""Stable facade for encounter action-option construction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..creature_control import available_creature_actions
from ..encounter_models.actions import EncounterAction
from ..participants import creature_controller
from ..reaction_runtime.damage_rerolls import reroll_damage_actions
from ..reaction_runtime.opportunity_offers import reaction_actions
from .option_discovery.spell_areas import (
    spell_area,
    spell_area_targets,
    targets_in_area,
)
from .option_discovery.spell_selection import spell_target_selection_actions
from .option_discovery.spell_targets import (
    spell_action_targets,
    spell_target_context,
)
from .option_discovery.spellcasting import (
    spell_action_cost,
    spell_cast_block_reason_for,
    spell_range_squares_for,
    spell_targets_self_only_for,
    spend_spell_resources,
)
from .option_discovery.spells import (
    available_spell_actions,
)
from .option_discovery.standard import (
    available_feature_actions,
    feature_action_available,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def available_actions(state: EncounterState) -> list[EncounterAction]:
    """Discover and normalize every action candidate for the current decision actor.

    Scripted controllers do not advertise choices to clients, while specialized
    decision frames delegate to their matching reaction service.

    >>> from types import SimpleNamespace
    >>> decision = SimpleNamespace(creature_ref="hero", kind="turn")
    >>> scripted = SimpleNamespace(current_decision=lambda: decision)
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.options.creature_controller",
    ...     return_value="scripted",
    ... ):
    ...     scripted_actions = available_actions(scripted)
    >>> scripted_actions
    []
    >>> decision.kind = "reroll_dice"
    >>> external = SimpleNamespace(current_decision=lambda: decision)
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.options.creature_controller",
    ...     return_value="external",
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.options.reroll_damage_actions",
    ...     return_value=[EncounterAction("Accept", "accept_roll")],
    ... ):
    ...     external_actions = available_actions(external)
    >>> external_actions[0].kind
    'accept_roll'
    """

    decision = state.current_decision()
    if creature_controller(state, decision.creature_ref) != "external":
        return []
    if decision.kind == "reroll_dice":
        return reroll_damage_actions(state)
    if decision.kind == "reaction":
        return reaction_actions(state)
    if decision.kind == "spell_targets":
        return spell_target_selection_actions(state, decision.creature_ref)
    return available_creature_actions(state, decision.creature_ref)


__all__ = [
    "available_actions",
    "available_feature_actions",
    "available_spell_actions",
    "feature_action_available",
    "spell_action_cost",
    "spell_action_targets",
    "spell_area",
    "spell_area_targets",
    "spell_cast_block_reason_for",
    "spell_range_squares_for",
    "spell_target_context",
    "spell_target_selection_actions",
    "spell_targets_self_only_for",
    "spend_spell_resources",
    "targets_in_area",
]
