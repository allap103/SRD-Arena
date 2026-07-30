from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ...creatures import (
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
    can_grapple,
)
from ...geometry import Position
from ..behaviors import DIRECTION_DELTAS, chebyshev_distance
from ..models import CreatureRef, EncounterAction
from .attack_resolution import attack_range_squares, has_free_hand
from .stat_block import (
    executable_multiattack_slot_plans,
    stat_block_action_resource_available,
    stat_block_action_runtime_issue,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


@dataclass(frozen=True)
class EligibilityFailure:
    code: str
    message: str


@dataclass(frozen=True)
class ActionEligibility:
    failures: tuple[EligibilityFailure, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.failures


class EligibilityRule(Protocol):
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None: ...


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
        if action.kind != "wait" and any(
            state.has_condition(actor_ref, condition)
            for condition in ("incapacitated", "stunned", "unconscious")
        ):
            return EligibilityFailure(
                "actor_incapacitated",
                "An incapacitated creature cannot take this action.",
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


class AttackRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
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
            return None
        if actor.actions_remaining <= 0 and actor.attacks_remaining <= 0:
            return EligibilityFailure("action_spent", "No attack remains.")
        target_failure = _opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        assert isinstance(action.value, str)
        preferred_attack_name = (
            action.preferred_attack_name
            if actor.pending_multiattack
            else action.preferred_attack_name
        )
        if actor.pending_multiattack and preferred_attack_name not in {
            invocation.name
            for invocation in actor.pending_multiattack[0].options
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
            preferred_attack_type=action.preferred_attack_type,
            preferred_attack_name=preferred_attack_name,
        )
        if (
            chebyshev_distance(
                actor.position,
                state._creature_position(action.value),
            )
            > reach
        ):
            return EligibilityFailure(
                "target_out_of_range", "The target is out of range."
            )
        return None


class GrappleRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        if action.kind != "grapple":
            return None
        actor = state.creatures[actor_ref]
        if actor.actions_remaining <= 0 and actor.attacks_remaining <= 0:
            return EligibilityFailure("action_spent", "No attack remains.")
        target_failure = _opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        assert isinstance(action.value, str)
        target = state.creatures[action.value]
        if chebyshev_distance(actor.position, target.position) != 1:
            return EligibilityFailure(
                "target_out_of_range", "The target is out of reach."
            )
        if not has_free_hand(actor.creature):
            return EligibilityFailure("free_hand_required", "A free hand is required.")
        if not can_grapple(target.creature.size, actor.creature.size):
            return EligibilityFailure("target_too_large", "The target is too large.")
        return None


class StatBlockActionRule:
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
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
                "unsupported_stat_block_mechanics",
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
        target_failure = _opposing_target_failure(state, actor_ref, action)
        if target_failure is not None:
            return target_failure
        target = state.creatures[action.value]
        if definition.target.kind == "area" and definition.target.origin == "self":
            return None
        range_feet = definition.target.range_feet or 0
        range_squares = (range_feet + 4) // 5
        if chebyshev_distance(actor.position, target.position) > range_squares:
            return EligibilityFailure(
                "target_out_of_range",
                "The target is out of range.",
            )
        return None


ACTION_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    ActorOwnershipRule(),
    ActorReadyRule(),
    ResourceRule(),
    MovementRule(),
    AttackRule(),
    GrappleRule(),
    StatBlockActionRule(),
)


def action_eligibility(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> ActionEligibility:
    failures = tuple(
        failure
        for rule in ACTION_ELIGIBILITY_RULES
        if (failure := rule.check(state, actor_ref, action)) is not None
    )
    return ActionEligibility(failures)


def require_action_eligible(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> None:
    eligibility = action_eligibility(state, actor_ref, action)
    if eligibility.allowed:
        return
    raise ValueError(eligibility.failures[0].message)


def _opposing_target_failure(
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
