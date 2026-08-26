"""Project encounter actions into display-ready action views."""

from ...domain.creatures.feature_actions import FeatureActionDefinition
from ...runtime.models import ActionView
from ...runtime.session import Session


def build_feature_actions(
    session: Session,
    story_actions: list[ActionView],
) -> list[ActionView]:
    if session.encounter_state is None:
        return []
    creature_ref = session.encounter_state.current_decision().creature_ref
    creature = session.encounter_state.creatures[creature_ref].creature
    available_feature_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "feature" and isinstance(action.value, str)
    }
    feature_actions: list[ActionView] = []
    for feature_id, definition in creature.combat_profile.feature_actions.items():
        available_action = available_feature_actions.get(feature_id)
        if available_action is not None:
            feature_actions.append(available_action)
            continue
        feature_actions.append(
            _build_unavailable_feature_action(definition, creature_ref)
        )
    return feature_actions


def _build_unavailable_feature_action(
    definition: FeatureActionDefinition,
    creature_ref: str,
) -> ActionView:
    cost = {definition.economy: 1} if definition.economy else {}
    return ActionView(
        id=f"{creature_ref}-feature-{definition.feature_id.replace('_', '-')}",
        label=definition.label,
        kind="feature",
        creature_ref=creature_ref,
        value=definition.feature_id,
        cost=cost,
        enabled=False,
        unavailable_reason="This feature is not currently available.",
        availability="unavailable",
        unavailable_reasons=("This feature is not currently available.",),
    )
