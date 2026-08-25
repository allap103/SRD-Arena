from __future__ import annotations

from typing import TYPE_CHECKING

from ...capabilities import ConditionRequirement, CreatureTypeRequirement
from ...effects.conditions import CombatTrait, Condition
from ...geometry import Position
from ..behaviors import DIRECTION_DELTAS
from ..models import CreatureRef, EncounterAction
from .eligibility_models import EligibilityFailure

if TYPE_CHECKING:
    from ..encounter import EncounterState


class ActorReadyRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
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
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        if action.creature_ref != actor_ref:
            return EligibilityFailure(
                "wrong_actor",
                f"The action belongs to '{action.creature_ref}', not '{actor_ref}'.",
            )
        return None


class ResourceRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        actor = state.creatures[actor_ref]
        if action.cost.movement > (actor.movement_remaining or 0):
            return EligibilityFailure(
                "insufficient_movement",
                "Not enough movement remains.",
            )
        if action.cost.action > actor.actions_remaining:
            return EligibilityFailure("action_spent", "No Action remains.")
        if action.cost.bonus_action and not actor.bonus_action_available:
            return EligibilityFailure(
                "bonus_action_spent",
                "No Bonus Action remains.",
            )
        if action.cost.reaction and not actor.reaction_available:
            return EligibilityFailure("reaction_spent", "No Reaction remains.")
        return None


class MovementRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        if action.kind != "move":
            return None
        if not isinstance(action.value, str) or action.value not in DIRECTION_DELTAS:
            return EligibilityFailure(
                "invalid_direction",
                "Movement requires a valid direction.",
            )
        movement_cost = state._movement_cost_for(actor_ref)
        actor = state.creatures[actor_ref]
        if movement_cost is None or (actor.movement_remaining or 0) < movement_cost:
            return EligibilityFailure(
                "insufficient_movement",
                "Not enough movement remains.",
            )
        dx, dy = DIRECTION_DELTAS[action.value]
        moving_refs = {actor_ref, *state._grappling_targets_for(actor_ref)}
        destinations = [
            Position(
                state._creature_position(moving_ref).x + dx,
                state._creature_position(moving_ref).y + dy,
            )
            for moving_ref in moving_refs
        ]
        if any(
            not state._position_is_free(
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
    if not isinstance(action.value, str):
        return EligibilityFailure("target_required", "A creature target is required.")
    target = state.creatures.get(action.value)
    if target is None or not target.is_alive:
        return EligibilityFailure("target_unavailable", "The target is not available.")
    if not state._creatures_are_opponents(actor_ref, action.value):
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
