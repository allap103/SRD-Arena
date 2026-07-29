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


def test_game_is_the_command_entrypoint_for_scene_choices() -> None:
    game = Game.start(ScenarioLoader().load(FIXTURE_ENCOUNTER_DIR))
    view = game.view()
    if game.encounter_state is not None and game.encounter_state.needs_ai_advance():
        game.advance_ai()
        view = game.view()
    action = next(
        action
        for action in view.action_details
        if not action.kind.startswith("system_")
    )

    result = game.choose(action.index)

    assert result.selected_action_id == action.id
