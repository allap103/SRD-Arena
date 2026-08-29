"""Validate actor ownership, readiness, resources, movement, and target predicates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import ConditionRequirement, CreatureTypeRequirement
from srd_arena.domain.effects.conditions import CombatTrait, Condition
from srd_arena.domain.geometry import Position

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import (
    CreatureRef,
    EncounterAction,
)
from ...grappling_state import grappling_targets_for, movement_cost_for
from ...participants import creatures_are_opponents
from ...state_runtime import creature_position, position_is_free
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class ActorReadyRule:
    """Reject actions by defeated creatures or creatures unable to act."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Reject actions by defeated or incapacitated actors.

        >>> from unittest.mock import Mock
        >>> actor = Mock(is_alive=False)
        >>> ActorReadyRule().check(Mock(creatures={"hero": actor}), "hero",
        ...     EncounterAction("Wait", "wait", creature_ref="hero")).code
        'actor_defeated'
        """
        actor = state.creatures[actor_ref]
        if not actor.is_alive:
            return EligibilityFailure(
                "actor_defeated", "A defeated creature cannot act."
            )
        effective = state.effective_conditions_for(actor_ref)
        if action.kind != "wait" and effective.has_trait(
            CombatTrait.CANNOT_TAKE_ACTIONS
        ):
            return EligibilityFailure(
                "condition.cannot_take_actions",
                "An incapacitated creature cannot take this action.",
                effective.providers_for_trait(CombatTrait.CANNOT_TAKE_ACTIONS),
            )
        return None


class ActorOwnershipRule:
    """Reject actions whose recorded owner is not the current actor."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Reject actions owned by a different encounter creature.

        >>> from unittest.mock import Mock
        >>> action = EncounterAction("Wait", "wait", creature_ref="goblin")
        >>> ActorOwnershipRule().check(Mock(), "hero", action).code
        'wrong_actor'
        """
        if action.creature_ref != actor_ref:
            return EligibilityFailure(
                "wrong_actor",
                f"The action belongs to '{action.creature_ref}', not '{actor_ref}'.",
            )
        return None


class ResourceRule:
    """Reject actions that exceed the actor's remaining movement budget."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Reject an action whose movement cost exceeds the remaining budget.

        >>> from unittest.mock import Mock
        >>> from ...encounter_models.actions import ActionCost
        >>> from srd_arena.domain.geometry import MovementCost
        >>> action = EncounterAction("Move", "move", cost=ActionCost(movement=MovementCost(2)))
        >>> ResourceRule().check(Mock(creatures={"hero": Mock(movement_remaining=1)}),
        ...     "hero", action).code
        'insufficient_movement'
        """
        actor = state.creatures[actor_ref]
        if action.cost.movement > (actor.movement_remaining or 0):
            return EligibilityFailure(
                "insufficient_movement",
                "Not enough movement remains.",
            )
        return None


class MovementRule:
    """Validate movement direction, cost, carried creatures, and occupancy."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate movement direction, budget, and destination occupancy.

        >>> from unittest.mock import Mock
        >>> action = EncounterAction("Move", "move", value="sideways")
        >>> MovementRule().check(Mock(), "hero", action).code
        'invalid_direction'
        """
        if action.kind != "move":
            return None
        if not isinstance(action.value, str) or action.value not in DIRECTION_DELTAS:
            return EligibilityFailure(
                "invalid_direction",
                "Movement requires a valid direction.",
            )
        movement_cost = movement_cost_for(state, actor_ref)
        actor = state.creatures[actor_ref]
        if movement_cost is None or (actor.movement_remaining or 0) < movement_cost:
            return EligibilityFailure(
                "insufficient_movement",
                "Not enough movement remains.",
            )
        dx, dy = DIRECTION_DELTAS[action.value]
        moving_refs = {actor_ref, *grappling_targets_for(state, actor_ref)}
        destinations = [
            Position(
                creature_position(state, moving_ref).x + dx,
                creature_position(state, moving_ref).y + dy,
            )
            for moving_ref in moving_refs
        ]
        if any(
            not position_is_free(
                state,
                destination.x,
                destination.y,
                ignored_refs=moving_refs,
            )
            for destination in destinations
        ):
            return EligibilityFailure(
                "destination_blocked",
                "The destination is not free.",
            )
        return None


def opposing_target_failure(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> EligibilityFailure | None:
    """Return a failure when a rule requires the target to be an opponent.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(creatures={"ally": SimpleNamespace(is_alive=True)})
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.eligibility_rules.common."
    ...     "creatures_are_opponents", return_value=False
    ... ):
    ...     failure = opposing_target_failure(
    ...         state, "hero", EncounterAction("Target Ally", "attack", "ally")
    ...     )
    >>> failure.code if failure else None
    'target_not_opponent'
    """

    if not isinstance(action.value, str):
        return EligibilityFailure("target_required", "A creature target is required.")
    target = state.creatures.get(action.value)
    if target is None or not target.is_alive:
        return EligibilityFailure("target_unavailable", "The target is not available.")
    if not creatures_are_opponents(state, actor_ref, action.value):
        return EligibilityFailure(
            "target_not_opponent",
            "The target must belong to an opposing team.",
        )
    return None


def target_requirement_failure(
    state: EncounterState,
    actor_ref: CreatureRef,
    target_ref: CreatureRef,
    requirements: tuple[object, ...],
) -> EligibilityFailure | None:
    """Return the first authored target requirement the candidate violates.

    >>> from types import SimpleNamespace
    >>> requirement = CreatureTypeRequirement(("humanoid",))
    >>> target = SimpleNamespace(
    ...     creature=SimpleNamespace(
    ...         statistics=SimpleNamespace(creature_type="undead")
    ...     )
    ... )
    >>> state = SimpleNamespace(creatures={"target": target})
    >>> failure = target_requirement_failure(
    ...     state, "cleric", "target", (requirement,)
    ... )
    >>> failure.code if failure else None
    'target_creature_type_required'
    """

    for requirement in requirements:
        if isinstance(requirement, CreatureTypeRequirement):
            creature_type = state.creatures[
                target_ref
            ].creature.statistics.creature_type
            if creature_type in requirement.creature_types:
                continue
            labels = ", ".join(requirement.creature_types)
            return EligibilityFailure(
                "target_creature_type_required",
                f"The target must have one of these creature types: {labels}.",
            )
        if not isinstance(requirement, ConditionRequirement):
            continue
        required = tuple(Condition(condition) for condition in requirement.conditions)
        effective = state.effective_conditions_for(target_ref)
        provider_ids_by_condition = {
            condition: effective.providers_for(condition) for condition in required
        }
        if requirement.applied_by == "source":
            source_provider_ids = {
                applied.id
                for applied in state.conditions_for(target_ref)
                if applied.source_ref == actor_ref
            }
            matches = tuple(
                bool(set(provider_ids_by_condition[condition]) & source_provider_ids)
                for condition in required
            )
        else:
            matches = tuple(
                bool(provider_ids_by_condition[condition]) for condition in required
            )
        satisfied = all(matches) if requirement.match == "all" else any(matches)
        if satisfied:
            continue
        labels = ", ".join(condition.value for condition in required)
        return EligibilityFailure(
            "target_condition_required",
            f"The target must have the required condition: {labels}.",
        )
    return None
