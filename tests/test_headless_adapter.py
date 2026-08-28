from pathlib import Path

import pytest

from srd_arena.application.startup import GameStartup
from srd_arena.frontends.headless import HeadlessGameAdapter
from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository

SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def _adapter() -> HeadlessGameAdapter:
    return HeadlessGameAdapter(
        GameStartup(FilesystemScenarioRepository(scenario_root=SCENARIOS_ROOT))
    )


def test_headless_adapter_drives_game_by_stable_ids() -> None:
    adapter = _adapter()
    scenarios = adapter.available_scenarios()

    assert any(scenario.id == "full_control_showcase" for scenario in scenarios)

    observation = adapter.start_scenario("full_control_showcase")
    assert observation.encounter is not None
    decision_id = observation.encounter.decision.id
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )
    assert wait.id in adapter.available_action_ids()

    result = adapter.select_action(
        wait.id,
        expected_decision_id=decision_id,
    )

    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == wait.id
    assert result.update.observation.encounter is not None


def test_headless_adapter_preserves_stale_decision_protection() -> None:
    adapter = _adapter()
    observation = adapter.start_scenario("full_control_showcase")
    assert observation.encounter is not None
    old_decision_id = observation.encounter.decision.id
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )
    accepted = adapter.select_action(
        wait.id,
        expected_decision_id=old_decision_id,
    )
    assert accepted.update is not None

    stale = adapter.select_action(
        wait.id,
        expected_decision_id=old_decision_id,
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_headless_adapter_requires_a_started_game() -> None:
    adapter = _adapter()

    with pytest.raises(RuntimeError, match="Start a scenario"):
        adapter.observe()

    with pytest.raises(KeyError, match="Unknown scenario"):
        adapter.start_scenario("missing")
