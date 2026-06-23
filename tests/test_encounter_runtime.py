from pathlib import Path

from game.encounter import EncounterAction
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
    assert "Movement remaining: 6/6 squares" in scene_view.scene_text
    assert "Player HP:" in scene_view.scene_text
    assert "Move up" in scene_view.choices
    assert "Move up-right" in scene_view.choices
    assert "Wait" in scene_view.choices
    assert "Flee encounter" in scene_view.choices
    assert "Retreat until the encounter system is ready." not in scene_view.choices


def test_goblin_encounter_movement_consumes_movement_before_turn_advances() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    move_up_index = scene_view.choices.index("Move up")
    result = session.choose(move_up_index)

    assert ("system", "You move up. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 1
    assert session.encounter_state.player_position.y == 5
    assert session.encounter_state.player_movement_remaining == 5
    assert session.encounter_state.enemies[0].position.x == 5
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.enemies[1].position.x == 6
    assert session.encounter_state.enemies[1].position.y == 2
    assert session.encounter_state.enemies[2].position.x == 4
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1


def test_goblin_encounter_allows_diagonal_movement() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_index = session.get_scene_view().choices.index("Move up-right")
    result = session.choose(move_index)

    assert ("system", "You move up-right. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 2
    assert session.encounter_state.player_position.y == 5


def test_spending_last_movement_square_does_not_auto_end_turn() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    for _ in range(6):
        scene_view = session.get_scene_view()
        move_right_index = scene_view.choices.index("Move right")
        result = session.choose(move_right_index)

    assert ("system", "You move right. Movement remaining: 0.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1
    assert session.get_scene_view().choices.count("Wait") == 1


def test_goblin_encounter_wait_advances_enemy_turns() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_up_index = session.get_scene_view().choices.index("Move up")
    session.choose(move_up_index)
    wait_index = session.get_scene_view().choices.index("Wait")
    result = session.choose(wait_index)

    assert ("system", "You hold your ground.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.enemies[0].position.x == 2
    assert session.encounter_state.enemies[0].position.y == 5
    assert session.encounter_state.enemies[1].position.x == 3
    assert session.encounter_state.enemies[1].position.y == 5
    assert session.encounter_state.enemies[2].position.x == 4
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 2


def test_advance_until_next_decision_runs_enemy_turns_until_player_turn() -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.turn_index = 1

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.transition is None
    assert ("system", "Goblin moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.active_actor() == ("player", None)
    assert session.encounter_state.round_number == 2


def test_enemy_movement_can_pause_for_player_opportunity_attack(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 2
    session.encounter_state.player_position.y = 2
    session.encounter_state.enemies[0].position.x = 3
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.turn_index = 1

    def scripted_behavior():
        context = yield None
        while True:
            context = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.paused_for_decision is True
    assert session.encounter_state.current_decision().kind == "reaction"
    labels = [action.label for action in session.encounter_state.available_actions(session.player)]
    assert labels == ["Opportunity attack Goblin", "Pass reaction"]

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 1)

    reaction = session.encounter_state.available_actions(session.player)[0]
    reaction_progress = session.encounter_state.apply_action(session.player, reaction)

    assert any("Opportunity attack hits" in message for _, message in reaction_progress.messages)
    assert session.encounter_state.enemies[0].position.x > 3
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.pending_action is None
    assert session.encounter_state.current_decision().actor_ref == "player"


def test_goblin_encounter_allows_diagonal_attacks(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 5
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 4)

    scene_view = session.get_scene_view()
    attack_index = next(
        index
        for index, choice in enumerate(scene_view.choices)
        if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.selected_choice_text.startswith("Attack enemy 1")
    assert any("Enemy 1 hits" in message for _, message in result.messages)


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
    assert loaded.encounter_state.enemies[0].position.x == 5
    assert loaded.encounter_state.enemies[0].position.y == 2
    assert loaded.encounter_state.turn_index == 0
    assert loaded.encounter_state.round_number == 1
    assert loaded.encounter_state.player_movement_remaining == 5


def test_save_and_load_preserve_pending_reaction_state(tmp_path: Path) -> None:
    session = Game(str(SAMPLE_GAME_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 2
    session.encounter_state.player_position.y = 2
    session.encounter_state.enemies[0].position.x = 3
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.turn_index = 1

    def scripted_behavior():
        context = yield None
        while True:
            context = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior
    session.encounter_state.advance_until_next_decision(session.player)
    save_path = tmp_path / "reaction_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert loaded.encounter_state is not None
    assert loaded.encounter_state.current_decision().kind == "reaction"
    assert loaded.encounter_state.pending_action is not None
    assert loaded.encounter_state.pending_action.actor_ref == "enemy:0"
