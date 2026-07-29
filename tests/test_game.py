from pathlib import Path

import pytest

from srd_arena.runtime.game import Game
from srd_arena.runtime.scenario import ScenarioLoader

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def test_session_view_does_not_implicitly_start_encounter() -> None:
    session = ScenarioLoader().load(FIXTURE_ENCOUNTER_DIR).create_session()

    with pytest.raises(RuntimeError, match="before starting"):
        session.get_scene_view()

    assert session.encounter_state is None


def test_game_start_creates_runtime_session_from_loaded_scenario() -> None:
    scenario = ScenarioLoader().load(FIXTURE_ENCOUNTER_DIR)

    game = Game.start(scenario)

    assert game.scenario is scenario
    assert game.session.current_scene_id == scenario.start_scene
    assert game.player.id == "player"
    assert game.encounter_state is not None


def test_game_supports_headless_action_discovery_and_execution() -> None:
    game = Game.start(ScenarioLoader().load(FIXTURE_ENCOUNTER_DIR))
    if game.encounter_state is not None and game.encounter_state.requires_automatic_advance():
        game.advance_until_input_required()
    assert game.encounter_state is not None
    actions = game.encounter_state.actions.available(game.player)
    action = next(action for action in actions if action.kind == "wait")

    result = game.perform(action)

    assert result.selected_action_id == action.id
    assert any(event.type == "action_declared" for event in result.events)
