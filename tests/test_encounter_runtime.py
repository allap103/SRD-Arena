from pathlib import Path

from game.engine import Game
from game.save import load_from_file, save_to_file

SAMPLE_GAME_DIR = Path("sample_game")


def test_goblin_encounter_scene_generates_runtime_actions_and_grid() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    assert scene_view.scene_text is not None

    assert "P" in scene_view.scene_text
    assert "E" in scene_view.scene_text
    assert "Round 1 - Turn: Player" in scene_view.scene_text
    assert "Player HP:" in scene_view.scene_text
    assert "Move up" in scene_view.choices
    assert "Wait" in scene_view.choices
    assert "Flee encounter" in scene_view.choices
    assert "Retreat until the encounter system is ready." not in scene_view.choices


def test_goblin_encounter_turn_advances_enemy_behaviors_after_player_move() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    move_up_index = scene_view.choices.index("Move up")
    result = session.choose(move_up_index)

    assert ("system", "You move up.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 1
    assert session.encounter_state.player_position.y == 5
    assert session.encounter_state.enemies[0].position.x == 4
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.enemies[1].position.x == 5
    assert session.encounter_state.enemies[1].position.y == 2
    assert session.encounter_state.enemies[2].position.x == 5
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 2


def test_goblin_encounter_attack_can_end_scene_with_victory(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.current_health = 1
    session.encounter_state.enemies[1].actor.current_health = 0
    session.encounter_state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 4)

    scene_view = session.get_scene_view()
    attack_index = next(
        index for index, choice in enumerate(scene_view.choices) if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.selected_choice_text.startswith("Attack enemy 1")
    assert session.current_scene_id == "goblin_encounter_victory"
    assert result.scene_changed is True


def test_save_and_load_preserve_encounter_progress(tmp_path: Path) -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    move_up_index = session.get_scene_view().choices.index("Move up")
    session.choose(move_up_index)
    save_path = tmp_path / "encounter_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert loaded.encounter_state is not None
    assert loaded.current_scene_id == "goblin_encounter"
    assert loaded.encounter_state.player_position.x == 1
    assert loaded.encounter_state.player_position.y == 5
    assert loaded.encounter_state.enemies[0].position.x == 4
    assert loaded.encounter_state.enemies[0].position.y == 2
    assert loaded.encounter_state.turn_index == 0
    assert loaded.encounter_state.round_number == 2
