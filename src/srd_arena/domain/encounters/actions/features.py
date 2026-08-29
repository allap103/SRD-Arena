"""Execute creature-feature actions after shared eligibility checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures.feature_actions import FeatureActionDefinition
from ...creatures.feature_rules import (
    resolve_feature_action as _resolve_feature_action_impl,
)
from ...effects.results import ActionResolutionResult
from ..attack_economy import clear_attack_action, consume_action
from ..encounter_models.resolution import EncounterProgress
from ..state_runtime import create_event
from .eligibility_rules.models import EligibilityFailure
from .rejections import reject_action

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_feature_action(
    state: EncounterState,
    creature: Creature,
    feature_id: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Dispatch a supported creature feature to its registered Python rule.

    Unknown feature IDs resolve as explicit failures instead of disappearing
    from the encounter log.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     combat_profile=SimpleNamespace(feature_actions={})
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="hero"),
    ...     event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_feature_action(state, creature, "unknown", progress, "feature-1")
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'unknown is not implemented yet.'), 'feature_unavailable')
    """

    creature_ref = state.current_decision().creature_ref
    feature_action = creature.combat_profile.feature_actions.get(feature_id)
    failure = _feature_execution_failure(
        state,
        creature,
        creature_ref,
        feature_id,
        feature_action,
    )
    if failure is not None:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="feature",
            message=failure.message,
            reason_code=failure.code,
            details={
                "feature_id": feature_id,
                "provider_state_ids": list(failure.state_ids),
            },
        )
        return
    assert feature_action is not None

    result = _resolve_feature_action_impl(
        creature,
        feature_id,
        state.dice.roll_die,
        lambda amount: state.combat_rules.apply_healing(
            state,
            creature_ref,
            amount,
        ),
        actor_ref=creature_ref,
    )
    if result is None:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="feature",
            message=f"{feature_action.label} is not implemented yet.",
            reason_code="feature_unimplemented",
            details={
                "feature_id": feature_id,
                "feature_name": feature_action.label,
            },
        )
        return

    if feature_action.economy == "bonus_action":
        state.active_bonus_action_available = False
    elif feature_action.economy == "action":
        consume_action(state, allow_magic=False)
        clear_attack_action(state.active_creature_state)
    elif feature_action.economy == "reaction":
        state.active_reaction_available = False

    progress.messages.extend(result.messages)
    granted_actions = result.details.get("grant_actions", 0)
    if isinstance(granted_actions, int) and granted_actions > 0:
        state.active_actions_remaining += granted_actions
    progress.events.append(
        create_event(
            state,
            "feature_used",
            creature_ref=creature_ref,
            action_id=action_id,
            data=_feature_event_data(
                creature,
                creature_ref,
                feature_id,
                result,
                granted_actions,
            ),
        )
    )


def _feature_execution_failure(
    state: EncounterState,
    creature: Creature,
    creature_ref: str,
    feature_id: str,
    feature_action: FeatureActionDefinition | None,
) -> EligibilityFailure | None:
    """Return the first defensive feature validation failure."""

    if feature_action is None:
        return EligibilityFailure(
            "feature_unavailable",
            f"{feature_id} is not implemented yet.",
        )
    if (
        feature_action.economy == "bonus_action"
        and not state.active_bonus_action_available
    ):
        return EligibilityFailure(
            "bonus_action_spent",
            "You have already used your Bonus Action.",
        )
    if feature_action.economy == "action" and state.active_actions_remaining <= 0:
        return EligibilityFailure(
            "action_spent",
            "You have already used your Action.",
        )
    if feature_action.economy == "reaction":
        reaction = state.combat_rules.reaction_eligibility(
            state,
            creature_ref,
            "feature",
        )
        if not reaction.allowed:
            return reaction.failures[0]
    if creature.feature_uses_remaining.get(feature_id, 0) <= 0:
        return EligibilityFailure(
            "resource_spent",
            f"You have no uses of {feature_action.label} remaining.",
        )
    return None


def _feature_event_data(
    creature: Creature,
    creature_ref: str,
    feature_id: str,
    result: ActionResolutionResult,
    granted_actions: object,
) -> dict[str, object]:
    """Build the successful feature event after its rule has resolved."""

    healing_effect = next(
        (effect for effect in result.effects if effect.kind == "healing"),
        None,
    )
    healing_data = healing_effect.data if healing_effect is not None else {}
    return {
        "kind": "feature",
        "feature_id": result.definition_id,
        "feature_name": result.definition_name,
        "target_ref": (
            healing_effect.target_ref if healing_effect is not None else creature_ref
        ),
        "target_label": healing_data.get("target_label", creature.name),
        "success": True,
        "healing": healing_data.get("amount", 0),
        "healing_roll_detail": healing_data.get("roll", {}),
        "uses_remaining": result.resource_updates.get(feature_id),
        "granted_actions": granted_actions if isinstance(granted_actions, int) else 0,
        "effects": [
            {
                "kind": effect.kind,
                "target_ref": effect.target_ref,
                "success": effect.success,
                "data": effect.data,
            }
            for effect in result.effects
        ],
    }
