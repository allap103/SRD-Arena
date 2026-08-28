"""Validate attack and grapple candidates against economy, targets, and reach."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import AttackActionDefinition, can_grapple
from ....geometry import grid_distance_between
from ...encounter_models.actions import (
    CreatureRef,
    EncounterAction,
)
from ...state_runtime import creature_position
from ..attack_resolution import attack_range_squares, has_free_hand
from ..stat_block import (
    executable_multiattack_slot_plans,
    stat_block_action_resource_available,
    stat_block_action_runtime_issue,
)
from .common import opposing_target_failure, target_requirement_failure
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class AttackRule:
    """Reject attacks lacking economy, a legal target, supported mechanics, or range."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate attack economy, target, capability, and range.

        >>> from unittest.mock import Mock
        >>> actor = Mock(actions_remaining=0, attacks_remaining=0)
        >>> action = EncounterAction("Strike", "attack", value="goblin")
        >>> AttackRule().check(Mock(creatures={"hero": actor}), "hero", action).code
        'action_spent'
        """
        if action.kind not in {"attack", "multiattack"}:
            return None
        actor = state.creatures[actor_ref]
        if action.kind == "multiattack":
            if actor.actions_remaining <= 0 or actor.attacks_remaining > 0:
                return EligibilityFailure("action_spent", "No Action remains.")
            plans = executable_multiattack_slot_plans(actor.creature)
            selected_plan = (
                int(action.value)
                if isinstance(action.value, str) and action.value.isdigit()
                else 0
            )
            if not plans or selected_plan >= len(plans):
                return EligibilityFailure(
                    "multiattack_unavailable",
                    "No executable Multiattack is available.",
                )
            unsupported = next(
                (
                    (invocation.name, issue)
                    for slot in plans[selected_plan]
                    for invocation in slot.options
                    if (
                        definition := actor.creature.stat_block_actions.get(
                            invocation.name
                        )
                    )
                    is not None
                    if (issue := stat_block_action_runtime_issue(definition))
                    is not None
                ),
                None,
            )
            if unsupported is not None:
                name, issue = unsupported
                return EligibilityFailure(
                    "unsupported_stat_block_capability",
                    f"{name}: {issue}",
                )
            return None
        if actor.actions_remaining <= 0 and actor.attacks_remaining <= 0:
            return EligibilityFailure("action_spent", "No attack remains.")
        target_failure = opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        assert isinstance(action.value, str)
        preferred_attack_name = action.preferred_attack_name
        if isinstance(preferred_attack_name, str):
            definition = actor.creature.stat_block_actions.get(preferred_attack_name)
            if definition is not None:
                runtime_issue = stat_block_action_runtime_issue(definition)
                if runtime_issue is not None:
                    return EligibilityFailure(
                        "unsupported_stat_block_capability",
                        runtime_issue,
                    )
                if isinstance(definition, AttackActionDefinition):
                    requirement_failure = target_requirement_failure(
                        state,
                        actor_ref,
                        action.value,
                        definition.target.requirements,
                    )
                    if requirement_failure is not None:
                        return requirement_failure
        if actor.pending_multiattack and preferred_attack_name not in {
            invocation.name for invocation in actor.pending_multiattack[0].options
        }:
            return EligibilityFailure(
                "multiattack_choice_unavailable",
                "That attack is not available for this Multiattack slot.",
            )
        if (
            isinstance(preferred_attack_name, str)
            and preferred_attack_name in actor.creature.stat_block_actions
            and not stat_block_action_resource_available(
                actor.creature,
                preferred_attack_name,
            )
        ):
            return EligibilityFailure(
                "resource_spent",
                f"{preferred_attack_name} is not available.",
            )
        reach = attack_range_squares(
            actor.creature,
            state.item_templates,
            state.definition.grid,
            preferred_attack_type=action.preferred_attack_type,
            preferred_attack_name=preferred_attack_name,
        )
        if (
            grid_distance_between(
                actor.position,
                creature_position(state, action.value),
            )
            > reach
        ):
            return EligibilityFailure(
                "target_out_of_range", "The target is out of range."
            )
        return None


class GrappleRule:
    """Reject grapples lacking economy, reach, a free hand, or a valid-sized target."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate grapple economy, target, reach, hand, and relative size.

        >>> from unittest.mock import Mock
        >>> actor = Mock(actions_remaining=0, attacks_remaining=0)
        >>> action = EncounterAction("Grapple", "grapple", value="goblin")
        >>> GrappleRule().check(Mock(creatures={"hero": actor}), "hero", action).code
        'action_spent'
        """
        if action.kind != "grapple":
            return None
        actor = state.creatures[actor_ref]
        if actor.actions_remaining <= 0 and actor.attacks_remaining <= 0:
            return EligibilityFailure("action_spent", "No attack remains.")
        target_failure = opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        assert isinstance(action.value, str)
        target = state.creatures[action.value]
        if grid_distance_between(actor.position, target.position) != 1:
            return EligibilityFailure(
                "target_out_of_range", "The target is out of reach."
            )
        if not has_free_hand(actor.creature):
            return EligibilityFailure("free_hand_required", "A free hand is required.")
        if not can_grapple(target.creature.size, actor.creature.size):
            return EligibilityFailure("target_too_large", "The target is too large.")
        return None
