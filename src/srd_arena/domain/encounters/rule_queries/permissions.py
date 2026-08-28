"""Encounter queries for reactions and turn action compatibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.condition_rules import effective_conditions
from ...effects.conditions import CombatTrait
from ...effects.rule_effects import (
    ActionEconomyKind,
    ActionEconomyRestriction,
    ReactionProhibition,
)
from ..actions.eligibility_rules.models import ActionEligibility, EligibilityFailure
from ..models import CreatureRef, EncounterAction
from .models import SourcedEligibilityFailure
from .providers import ongoing_rule_effects

if TYPE_CHECKING:
    from ..encounter import EncounterState


def reaction_eligibility(
    state: EncounterState,
    creature_ref: CreatureRef,
    reaction_kind: str | None = None,
) -> ActionEligibility:
    """Return every reason a creature cannot take the requested reaction.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(condition_immunities=lambda: frozenset())
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(
    ...         is_alive=True, reaction_available=False, creature=creature
    ...     )},
    ...     conditions=[], ongoing_effects=[],
    ... )
    >>> [failure.code for failure in reaction_eligibility(state, "hero").failures]
    ['reaction_spent']
    """

    creature_state = state.creatures[creature_ref]
    failures: list[EligibilityFailure] = []
    if not creature_state.is_alive:
        failures.append(
            EligibilityFailure(
                "reactor_defeated",
                "A defeated creature cannot take reactions.",
            )
        )
    if not creature_state.reaction_available:
        failures.append(EligibilityFailure("reaction_spent", "No Reaction remains."))
    conditions = effective_conditions(
        tuple(
            condition
            for condition in state.conditions
            if condition.target_ref == creature_ref
        ),
        creature_state.creature.condition_immunities(),
    )
    if conditions.has_trait(CombatTrait.CANNOT_TAKE_REACTIONS):
        failures.append(
            EligibilityFailure(
                "condition.cannot_take_reactions",
                "This creature cannot take reactions.",
                conditions.providers_for_trait(CombatTrait.CANNOT_TAKE_REACTIONS),
            )
        )
    failures.extend(
        SourcedEligibilityFailure(
            "effect.cannot_take_reactions",
            "An ongoing effect prevents this reaction.",
            (provider_state_id,),
            (source,),
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, ReactionProhibition)
        and (
            not rule_effect.reaction_kinds
            or (
                reaction_kind is not None
                and reaction_kind in rule_effect.reaction_kinds
            )
        )
    )
    return ActionEligibility(tuple(failures))


def action_compatibility(
    state: EncounterState,
    creature_ref: CreatureRef,
    action: EncounterAction,
) -> ActionEligibility:
    """Ask whether current permissions and turn economy permit an action.

    >>> from types import SimpleNamespace
    >>> from ..models import ActionCost
    >>> creature = SimpleNamespace(condition_immunities=lambda: frozenset())
    >>> creature_state = SimpleNamespace(
    ...     is_alive=True, creature=creature, actions_remaining=0,
    ...     bonus_action_available=True, reaction_available=True,
    ...     action_used_this_turn=False, bonus_action_used_this_turn=False,
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": creature_state}, conditions=[], ongoing_effects=[]
    ... )
    >>> action = EncounterAction(
    ...     "Attack", "attack", creature_ref="hero", cost=ActionCost(action=1)
    ... )
    >>> [failure.code for failure in action_compatibility(
    ...     state, "hero", action
    ... ).failures]
    ['action_spent']
    """

    creature_state = state.creatures[creature_ref]
    failures: list[EligibilityFailure] = []
    if action.creature_ref != creature_ref:
        failures.append(
            EligibilityFailure(
                "wrong_actor",
                f"The action belongs to '{action.creature_ref}', not '{creature_ref}'.",
            )
        )
    if not creature_state.is_alive:
        failures.append(
            EligibilityFailure("actor_defeated", "A defeated creature cannot act.")
        )
    conditions = effective_conditions(
        tuple(
            condition
            for condition in state.conditions
            if condition.target_ref == creature_ref
        ),
        creature_state.creature.condition_immunities(),
    )
    if action.kind != "wait" and conditions.has_trait(CombatTrait.CANNOT_TAKE_ACTIONS):
        failures.append(
            EligibilityFailure(
                "condition.cannot_take_actions",
                "An incapacitated creature cannot take this action.",
                conditions.providers_for_trait(CombatTrait.CANNOT_TAKE_ACTIONS),
            )
        )
    if action.cost.action > creature_state.actions_remaining:
        failures.append(EligibilityFailure("action_spent", "No Action remains."))
    if action.cost.bonus_action and not creature_state.bonus_action_available:
        failures.append(
            EligibilityFailure("bonus_action_spent", "No Bonus Action remains.")
        )
    if action.cost.reaction:
        failures.extend(
            reaction_eligibility(
                state,
                creature_ref,
                reaction_kind=action.kind,
            ).failures
        )
    for provider_state_id, source, rule_effect in ongoing_rule_effects(
        state, creature_ref
    ):
        if not isinstance(rule_effect, ActionEconomyRestriction):
            continue
        restricted = rule_effect.choose_between
        uses_action = bool(action.cost.action)
        uses_bonus_action = bool(action.cost.bonus_action)
        conflicts = (
            (
                uses_action
                and ActionEconomyKind.ACTION in restricted
                and ActionEconomyKind.BONUS_ACTION in restricted
                and creature_state.bonus_action_used_this_turn
            )
            or (
                uses_bonus_action
                and ActionEconomyKind.BONUS_ACTION in restricted
                and ActionEconomyKind.ACTION in restricted
                and creature_state.action_used_this_turn
            )
            or (uses_action and uses_bonus_action)
        )
        if conflicts:
            failures.append(
                SourcedEligibilityFailure(
                    "effect.action_economy_conflict",
                    "An ongoing effect allows either an Action or a Bonus Action, not both.",
                    (provider_state_id,),
                    (source,),
                )
            )
    return ActionEligibility(_unique_failures(failures))


def _unique_failures(
    failures: list[EligibilityFailure],
) -> tuple[EligibilityFailure, ...]:
    unique: list[EligibilityFailure] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for failure in failures:
        key = failure.code, failure.state_ids
        if key in seen:
            continue
        seen.add(key)
        unique.append(failure)
    return tuple(unique)
