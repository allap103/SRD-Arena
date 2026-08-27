"""Validate stat-block and feature capability candidates before execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import AutomaticActionDefinition, SavingThrowActionDefinition
from ....geometry import grid_distance_between
from ...models import CreatureRef, EncounterAction
from ..stat_block import (
    stat_block_action_resource_available,
    stat_block_action_runtime_issue,
)
from .common import opposing_target_failure, target_requirement_failure
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class StatBlockActionRule:
    """Check stat-block implementation support, resources, targeting, and range."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate executable stat-block capability and its resources.

        >>> from unittest.mock import Mock
        >>> actor = Mock()
        >>> actor.creature.stat_block_actions = {}
        >>> action = EncounterAction("Roar", "stat_block", preferred_attack_name="roar")
        >>> StatBlockActionRule().check(
        ...     Mock(creatures={"dragon": actor}), "dragon", action).code
        'stat_block_action_unavailable'
        """
        if action.kind != "stat_block":
            return None
        actor = state.creatures[actor_ref]
        name = action.preferred_attack_name
        definition = actor.creature.stat_block_actions.get(name or "")
        if not isinstance(
            definition,
            (AutomaticActionDefinition, SavingThrowActionDefinition),
        ):
            return EligibilityFailure(
                "stat_block_action_unavailable",
                "The stat-block action is not executable.",
            )
        runtime_issue = stat_block_action_runtime_issue(definition)
        if runtime_issue is not None:
            return EligibilityFailure(
                "unsupported_stat_block_capability",
                runtime_issue,
            )
        if not stat_block_action_resource_available(
            actor.creature,
            definition.name,
        ):
            return EligibilityFailure(
                "resource_spent",
                f"{definition.name} is not available.",
            )
        if definition.target.kind == "area" and definition.target.origin == "self":
            if isinstance(action.value, tuple):
                aim_x, aim_y = action.value
                actor_center = (actor.position.x + 0.5, actor.position.y + 0.5)
                if (
                    abs(aim_x - actor_center[0]) < 1e-9
                    and abs(aim_y - actor_center[1]) < 1e-9
                ):
                    return EligibilityFailure(
                        "aim_required",
                        "The area must be aimed away from its user.",
                    )
                return None
            if isinstance(action.value, str):
                return opposing_target_failure(state, actor_ref, action)
            return EligibilityFailure(
                "target_required",
                "An aim point is required.",
            )
        if not isinstance(action.value, str):
            return EligibilityFailure(
                "target_required",
                "A creature target is required.",
            )
        if definition.target.kind == "self":
            if action.value != actor_ref:
                return EligibilityFailure(
                    "invalid_self_target",
                    "This action targets only its user.",
                )
            return None
        target_failure = opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        target = state.creatures[action.value]
        requirement_failure = target_requirement_failure(
            state,
            actor_ref,
            action.value,
            definition.target.requirements,
        )
        if requirement_failure is not None:
            return requirement_failure
        range_feet = definition.target.range_feet or 0
        range_squares = state.definition.grid.covering_distance_from_feet(range_feet)
        if grid_distance_between(actor.position, target.position) > range_squares:
            return EligibilityFailure(
                "target_out_of_range",
                "The target is out of range.",
            )
        return None


class FeatureActionRule:
    """Check that a feature action exists and retains a consumable use."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate that a feature action exists and retains uses.

        >>> from unittest.mock import Mock
        >>> creature = Mock()
        >>> creature.combat_profile.feature_actions = {}
        >>> action = EncounterAction("Feature", "feature", value="missing")
        >>> FeatureActionRule().check(
        ...     Mock(creatures={"hero": Mock(creature=creature)}), "hero", action).code
        'feature_unavailable'
        """
        if action.kind != "feature" or not isinstance(action.value, str):
            return None
        actor = state.creatures[actor_ref].creature
        definition = actor.combat_profile.feature_actions.get(action.value)
        if definition is None:
            return EligibilityFailure(
                "feature_unavailable",
                "This feature action is not executable.",
            )
        if actor.feature_uses_remaining.get(action.value, 0) <= 0:
            return EligibilityFailure(
                "resource_spent",
                f"No uses of {definition.label} remain.",
            )
        return None
