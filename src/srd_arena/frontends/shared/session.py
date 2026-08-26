"""Compose frontend-neutral presentation state for a runtime session."""

from __future__ import annotations

from typing import Any, cast

from ...runtime.models import SceneView
from ...runtime.session import Session
from .actions import build_feature_actions
from .battlefield import build_battlefield_view
from .config import EncounterPresentationConfig
from .models import EncounterView, SessionPresentation
from .resources import build_resource_summary

SYSTEM_ACTION_COUNT = 1


def build_session_presentation(
    session: Session,
    scene_view: SceneView | None = None,
    config: EncounterPresentationConfig | None = None,
) -> SessionPresentation:
    presentation_config = config or EncounterPresentationConfig()
    view = scene_view or session.get_scene_view()
    story_actions = view.action_details[:-SYSTEM_ACTION_COUNT]
    system_actions = view.action_details[-SYSTEM_ACTION_COUNT:]

    if session.encounter_state is None:
        return SessionPresentation(
            scene_id=view.scene_id,
            story_text=view.scene_text,
            story_actions=story_actions,
            system_actions=system_actions,
        )

    combat_state = cast(dict[str, Any], session.encounter_state.export_state())
    resources = build_resource_summary(combat_state)
    movement_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "move" and isinstance(action.value, str)
    }
    non_movement_actions = [
        action
        for action in story_actions
        if action.kind not in {"move", "wait", "pass"}
    ]
    feature_actions = build_feature_actions(session, story_actions)
    end_turn_action = next(
        (action for action in story_actions if action.kind in {"wait", "pass"}),
        None,
    )
    decision_kind = combat_state["decision"]["kind"]
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
                combat_state,
                background_image=presentation_config.background_image,
                grid_color=presentation_config.grid_color,
                grid_opacity=presentation_config.grid_opacity,
                team_ids=tuple(team.id for team in session.current_encounter.teams),
            ),
            resources=resources,
            movement_actions=movement_actions,
            non_movement_actions=non_movement_actions,
            feature_actions=feature_actions,
            end_turn_action=end_turn_action,
            action_pane_title=action_pane_title,
            transition_message=(
                session.pending_scene_transition.message
                if session.pending_scene_transition is not None
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
                if session.pending_scene_transition is not None
                else None
            ),
        ),
    )
