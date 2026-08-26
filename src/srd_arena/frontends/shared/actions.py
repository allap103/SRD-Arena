"""Project observed encounter actions into display-ready action views."""

from ...application.observations import (
    ActionObservation,
    ActionReasonObservation,
    EncounterObservation,
    FeatureActionObservation,
)


def build_feature_actions(
    encounter: EncounterObservation,
    story_actions: list[ActionObservation],
) -> list[ActionObservation]:
    creature_ref = encounter.decision.creature_ref
    creature = encounter.creature(creature_ref)
    available_feature_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "feature" and isinstance(action.value, str)
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
    return feature_actions


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
        value=definition.feature_id,
        cost=cost,
        enabled=False,
        availability="unavailable",
        reasons=(ActionReasonObservation(code="feature_unavailable", message=reason),),
    )
