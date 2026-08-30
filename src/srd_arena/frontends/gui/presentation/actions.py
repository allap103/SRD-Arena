"""Project observed encounter actions into display-ready GUI action views."""

from collections.abc import Sequence

from srd_arena.engine.api import (
    ActionObservation,
    ActionReasonObservation,
    EncounterObservation,
    FeatureActionObservation,
)


def build_feature_actions(
    encounter: EncounterObservation,
    story_actions: Sequence[ActionObservation],
) -> tuple[ActionObservation, ...]:
    """Select and order feature actions for the frontend action pane.

    Authored features remain visible even when no currently selectable action
    corresponds to them.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     feature_actions=(FeatureActionObservation("surge", "Second Wind", "bonus_action"),)
    ... )
    >>> encounter = SimpleNamespace(
    ...     decision=SimpleNamespace(creature_ref="hero"),
    ...     creature=lambda ref: creature,
    ... )
    >>> action = build_feature_actions(encounter, [])[0]
    >>> (action.label, action.enabled, action.cost)
    ('Second Wind', False, mappingproxy({'bonus_action': 1}))
    """

    creature_ref = encounter.decision.creature_ref
    creature = encounter.creature(creature_ref)
    available_feature_actions = {
        action.feature_id: action
        for action in story_actions
        if action.kind == "feature" and action.feature_id is not None
    }
    feature_actions: list[ActionObservation] = []
    for definition in creature.feature_actions:
        available_action = available_feature_actions.get(definition.feature_id)
        if available_action is not None:
            feature_actions.append(available_action)
            continue
        feature_actions.append(
            _build_unavailable_feature_action(definition, creature_ref)
        )
    return tuple(feature_actions)


def _build_unavailable_feature_action(
    definition: FeatureActionObservation,
    creature_ref: str,
) -> ActionObservation:
    cost = {definition.economy: 1} if definition.economy else {}
    reason = "This feature is not currently available."
    return ActionObservation(
        id=f"{creature_ref}-feature-{definition.feature_id.replace('_', '-')}",
        label=definition.label,
        kind="feature",
        creature_ref=creature_ref,
        feature_id=definition.feature_id,
        cost=cost,
        enabled=False,
        availability="unavailable",
        reasons=(ActionReasonObservation(code="feature_unavailable", message=reason),),
    )
