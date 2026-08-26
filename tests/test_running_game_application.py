from __future__ import annotations

from pathlib import Path
from typing import cast

from srd_arena.application.game import RunningGame
from srd_arena.application.observations import ActionObservation
from srd_arena.application.startup import GameStartup
from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository
from srd_arena.runtime.models import ActionView, SceneView, TurnResult
from srd_arena.runtime.session import Session

FULL_CONTROL_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)


class SessionStub:
    def __init__(self) -> None:
        self.encounter_state = None
        self.pending_scene_transition = None
        self.selected_action_ids: list[str] = []
        self.advance_count = 0
        self.reset_count = 0
        self.scene = SceneView(
            scene_id="arena",
            scene_text=None,
            action_details=[
                ActionView(
                    id="actor-wait",
                    label="Wait",
                    kind="wait",
                    creature_ref="actor",
                ),
                ActionView(
                    id="actor-blocked",
                    label="Blocked",
                    kind="attack",
                    creature_ref="actor",
                    enabled=False,
                    unavailable_reason="No Action remains.",
                    availability="unavailable",
                    unavailable_codes=("action_unavailable",),
                    unavailable_reasons=("No Action remains.",),
                ),
            ],
        )

    def get_scene_view(self) -> SceneView:
        return self.scene

    def choose(self, action_id: str) -> TurnResult:
        self.selected_action_ids.append(action_id)
        return TurnResult(scene=self.scene, selected_action_id=action_id)

    def advance_until_input_required(self) -> TurnResult:
        self.advance_count += 1
        return TurnResult(scene=self.scene)

    def reset(self) -> None:
        self.reset_count += 1


def _running_game(session: SessionStub) -> RunningGame:
    return RunningGame(
        scenario_directory=Path("arena"),
        items=(),
        session=cast(Session, session),
    )


def test_running_game_observes_controller_requirement() -> None:
    session = SessionStub()
    game = _running_game(session)

    observation = game.observe()

    assert observation.scene.scene_id == session.scene.scene_id
    assert observation.encounter is None
    assert observation.requires_automatic_advance is False
    assert isinstance(observation.scene.action_details[0], ActionObservation)
    assert observation.scene.action_details[1].reasons[0].code == "action_unavailable"
    assert (
        observation.scene.action_details[1].reasons[0].message == "No Action remains."
    )


def test_running_game_exposes_headless_decision_workflow() -> None:
    session = SessionStub()
    game = _running_game(session)
    action_id = game.observe().scene.action_details[0].id

    selected = game.select_action(action_id)
    advanced = game.advance_automatic()
    reset = game.reset()

    assert selected.selected_action_id == action_id
    assert advanced.scene is session.scene
    assert reset.scene.scene_id == session.scene.scene_id
    assert session.selected_action_ids == [action_id]
    assert session.advance_count == 1
    assert session.reset_count == 1


def test_headless_client_can_start_observe_and_select_by_stable_id() -> None:
    game = GameStartup(FilesystemScenarioRepository()).start_scenario(
        FULL_CONTROL_SCENARIO_DIR
    )
    observation = game.observe()
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = game.select_action(wait.id)
    next_observation = game.observe()

    assert observation.requires_automatic_advance is False
    assert observation.encounter is not None
    assert observation.encounter.decision.creature_ref
    assert observation.encounter.creatures
    assert result.selected_action_id == wait.id
    assert next_observation.scene.scene_id == observation.scene.scene_id
