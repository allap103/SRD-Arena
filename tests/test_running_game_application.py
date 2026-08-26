from __future__ import annotations

from pathlib import Path
from typing import cast

from srd_arena.application.commands import (
    AimAction,
    ConfirmTargeting,
    SelectAction,
    SetResourceAllocation,
)
from srd_arena.application.game import RunningGame
from srd_arena.application.observations import ActionObservation
from srd_arena.application.startup import GameStartup
from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository
from srd_arena.runtime.models import ActionView, SceneView, TurnResult
from srd_arena.runtime.session import Session

FULL_CONTROL_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)
MASS_HEAL_SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "mass_heal_allocation_showcase"
)
SPELL_DAMAGE_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "spell_damage_showcase"
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
    return RunningGame(cast(Session, session))


def _advance_to_actor(game: RunningGame, creature_ref: str):
    for _ in range(20):
        observation = game.observe()
        assert observation.encounter is not None
        if observation.encounter.decision.creature_ref == creature_ref:
            return observation
        wait = next(
            action
            for action in observation.scene.action_details
            if action.kind == "wait" and action.enabled
        )
        result = game.execute(
            SelectAction(wait.id, observation.encounter.decision.id)
        )
        assert result.update is not None
    raise AssertionError(f"Creature '{creature_ref}' did not receive a turn.")


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
    observation = game.observe()
    action_id = observation.scene.action_details[0].id

    selected = game.execute(SelectAction(action_id, expected_decision_id=None))
    advanced = game.advance_automatic()
    reset = game.reset()

    assert selected.update is not None
    assert selected.update.selected_action_id == action_id
    assert advanced.observation.scene.scene_id == session.scene.scene_id
    assert reset.scene.scene_id == session.scene.scene_id
    assert session.selected_action_ids == [action_id]
    assert session.advance_count == 1
    assert session.reset_count == 1


def test_running_game_can_start_observe_and_select_by_stable_id() -> None:
    game = GameStartup(FilesystemScenarioRepository()).start_scenario(
        FULL_CONTROL_SCENARIO_DIR.name
    )
    observation = game.observe()
    assert observation.encounter is not None
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = game.execute(
        SelectAction(wait.id, observation.encounter.decision.id)
    )
    next_observation = game.observe()

    assert observation.requires_automatic_advance is False
    assert observation.encounter.decision.creature_ref
    assert observation.encounter.creatures
    assert result.update is not None
    assert result.update.selected_action_id == wait.id
    assert next_observation.scene.scene_id == observation.scene.scene_id


def test_stale_application_command_is_rejected_without_reaching_engine() -> None:
    session = SessionStub()
    game = _running_game(session)

    result = game.execute(
        SelectAction(action_id="actor-wait", expected_decision_id="old-decision")
    )

    assert result.accepted is False
    assert result.failure is not None
    assert result.failure.code == "stale_decision"
    assert session.selected_action_ids == []

    unavailable = game.execute(
        SelectAction(action_id="actor-blocked", expected_decision_id=None)
    )
    assert unavailable.failure is not None
    assert unavailable.failure.code == "action_unavailable"
    assert session.selected_action_ids == []


def test_application_aims_an_advertised_area_action() -> None:
    game = GameStartup(FilesystemScenarioRepository()).start_scenario(
        SPELL_DAMAGE_SCENARIO_DIR.name
    )
    observation = _advance_to_actor(game, "spectrum_adept")
    assert observation.encounter is not None
    fireball = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell"
        and action.source_id == "fireball"
        and action.enabled
    )
    assert fireball.source_label == "Fireball"
    assert fireball.source_level == 3
    assert fireball.target_ref is None
    assert fireball.area_preview is not None
    assert fireball.area_preview["shape"] == "radius"
    assert not hasattr(fireball, "value")

    result = game.execute(
        AimAction(
            action_id=fireball.id,
            x=6.5,
            y=3.5,
            expected_decision_id=observation.encounter.decision.id,
        )
    )

    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == fireball.id


def test_application_controls_numeric_target_allocation() -> None:
    game = GameStartup(FilesystemScenarioRepository()).start_scenario(
        MASS_HEAL_SCENARIO_DIR.name
    )
    observation = game.observe()
    assert observation.encounter is not None
    cast = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.enabled
    )
    started = game.execute(SelectAction(cast.id, observation.encounter.decision.id))
    assert started.update is not None
    targeting = started.update.observation.encounter
    assert targeting is not None and targeting.targeting is not None
    assert targeting.targeting.resource_pool_total == 700

    allocation = game.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=200,
            expected_decision_id=targeting.decision.id,
        )
    )
    assert allocation.update is not None
    allocated_encounter = allocation.update.observation.encounter
    assert allocated_encounter is not None and allocated_encounter.targeting is not None
    assert allocated_encounter.targeting.resource_allocations[0].amount == 200

    invalid = game.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=201,
            expected_decision_id=allocated_encounter.decision.id,
        )
    )
    assert invalid.failure is not None
    assert invalid.failure.code == "invalid_allocation"

    confirmed = game.execute(
        ConfirmTargeting(expected_decision_id=allocated_encounter.decision.id)
    )
    assert confirmed.accepted is True
