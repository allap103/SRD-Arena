"""Compose frontend-neutral presentation state from an application observation."""

from __future__ import annotations

from srd_arena.application.api import GameObservation, ScenarioPresentation

from .actions import build_feature_actions
from .battlefield import build_battlefield_view
from .models import EncounterView, SessionPresentation
from .resources import build_resource_summary

SYSTEM_ACTION_COUNT = 1


def build_session_presentation(
    observation: GameObservation,
    config: ScenarioPresentation | None = None,
) -> SessionPresentation:
    """Convert one application observation into a complete frontend snapshot."""

    presentation_config = config or ScenarioPresentation()
    view = observation.scene
    story_actions = list(view.action_details[:-SYSTEM_ACTION_COUNT])
    system_actions = list(view.action_details[-SYSTEM_ACTION_COUNT:])

    if observation.encounter is None:
        return SessionPresentation(
            scene_id=view.scene_id,
            story_text=view.scene_text,
            story_actions=story_actions,
            system_actions=system_actions,
        )

    encounter = observation.encounter
    resources = build_resource_summary(encounter)
    movement_actions = {
        action.movement_direction: action
        for action in story_actions
        if action.kind == "move" and action.movement_direction is not None
    }
    non_movement_actions = [
        action
        for action in story_actions
        if action.kind not in {"move", "wait", "pass"}
    ]
    feature_actions = build_feature_actions(encounter, story_actions)
    end_turn_action = next(
        (action for action in story_actions if action.kind in {"wait", "pass"}),
        None,
    )
    decision_kind = encounter.decision.kind
    action_pane_title = (
        "Reactions"
        if decision_kind == "reaction"
        else "Reroll Damage"
        if decision_kind == "reroll_dice"
        else "Actions"
    )
    return SessionPresentation(
        scene_id=view.scene_id,
        story_text="",
        story_actions=story_actions,
        system_actions=system_actions,
        encounter=EncounterView(
            narrative_text="",
            battlefield=build_battlefield_view(
                encounter,
                background_image=presentation_config.background_image,
                grid_color=presentation_config.grid_color,
                grid_opacity=presentation_config.grid_opacity,
                team_ids=encounter.team_ids,
            ),
            resources=resources,
            movement_actions=movement_actions,
            non_movement_actions=non_movement_actions,
            feature_actions=feature_actions,
            end_turn_action=end_turn_action,
            action_pane_title=action_pane_title,
            transition_message=(
                observation.transition.message
                if observation.transition is not None
                else None
            ),
            transition_action=(
                next(
                    (
                        action
                        for action in story_actions
                        if action.kind == "system_continue_transition"
                    ),
                    None,
                )
                if observation.transition is not None
                else None
            ),
        ),
    )
