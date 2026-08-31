"""Discover universal combat actions and feature-provided action grants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.feature_actions import FeatureActionDefinition

from ...encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from ...rule_queries.permissions import reaction_eligibility

if TYPE_CHECKING:
    from ...encounter import EncounterState


def available_feature_actions(
    state: EncounterState,
    creature: Creature,
) -> list[EncounterAction]:
    """Advertise supported non-reaction feature actions for the current actor.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.creatures.feature_actions import FeatureActionDefinition
    >>> feature = FeatureActionDefinition(
    ...     "second_wind", "Second Wind", "bonus_action"
    ... )
    >>> creature = SimpleNamespace(
    ...     combat_profile=SimpleNamespace(
    ...         feature_actions={"second_wind": feature}
    ...     )
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="fighter")
    ... )
    >>> action = available_feature_actions(state, creature)[0]
    >>> (action.label, action.kind, action.cost.bonus_action)
    ('Second Wind', 'feature', 1)
    """

    creature_ref = state.current_decision().creature_ref
    actions: list[EncounterAction] = []
    for feature_id, definition in creature.combat_profile.feature_actions.items():
        if definition.economy == "reaction":
            continue
        action_cost = ActionCost(
            bonus_action=1 if definition.economy == "bonus_action" else 0,
            action=1 if definition.economy == "action" else 0,
            reaction=1 if definition.economy == "reaction" else 0,
        )
        actions.append(
            EncounterAction(
                definition.label,
                "feature",
                feature_id,
                id=f"{creature_ref}-feature-{feature_id.replace('_', '-')}",
                creature_ref=creature_ref,
                cost=action_cost,
            )
        )
    return actions


def feature_action_available(
    state: EncounterState,
    actor: Creature,
    definition: FeatureActionDefinition,
) -> bool:
    """Return whether a creature feature may currently supply its action.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.creatures.feature_actions import FeatureActionDefinition
    >>> feature = FeatureActionDefinition(
    ...     "second_wind", "Second Wind", "bonus_action"
    ... )
    >>> actor = SimpleNamespace(feature_uses_remaining={"second_wind": 1})
    >>> state = SimpleNamespace(
    ...     active_bonus_action_available=True, active_actions_remaining=1
    ... )
    >>> feature_action_available(state, actor, feature)
    True
    """

    if definition.economy == "bonus_action" and not state.active_bonus_action_available:
        return False
    if definition.economy == "action" and state.active_actions_remaining <= 0:
        return False
    if (
        definition.economy == "reaction"
        and not reaction_eligibility(
            state,
            state.current_decision().creature_ref,
            "feature",
        ).allowed
    ):
        return False
    return actor.feature_uses_remaining.get(definition.feature_id, 0) > 0
