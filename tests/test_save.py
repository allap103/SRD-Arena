import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from game.engine import Game
from game.save import (
    SaveGame,
    create_save,
    get_slot_path,
    load_from_file,
    load_from_slot,
    restore_save,
    save_to_file,
    save_to_slot,
)
from game.session import (
    EXIT_CHOICE_TEXT,
    LOAD_CHOICE_TEXT,
    LONG_REST_CHOICE_TEXT,
    SAVE_CHOICE_TEXT,
    SHORT_REST_CHOICE_TEXT,
)

FIXTURE_GAME_DIR = Path(__file__).parent / "fixtures" / "graph_game"
FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def test_create_save_captures_mutable_session_state() -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.current_scene_id = "shared_target"
    session.player.take_damage(3)
    session.player.inventory.add_item("found_key")
    session.player.equipment.equip("found_key", "left_hand")
    session.choice_resolver.completed_tests.add(("start", "Take the bright path."))

    save = create_save(session)

    assert save.version == 2
    assert save.current_scene_id == "shared_target"
    assert save.start_scene_id == "start"
    assert save.player.actor_id == "player"
    assert save.player.current_health == 9
    assert save.player.inventory == ["starter_item", "found_key"]
    assert save.player.equipment["left_hand"] == "found_key"
    assert save.completed_tests[0].scene_id == "start"
    assert save.completed_tests[0].choice_text == "Take the bright path."


def test_restore_save_reloads_content_and_applies_saved_state() -> None:
    original = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    original.current_scene_id = "shared_target"
    original.player.take_damage(4)
    original.player.inventory.add_item("map")
    original.choice_resolver.completed_tests.add(("start", "Take the quiet path."))

    restored = restore_save(create_save(original), FIXTURE_GAME_DIR)

    assert restored.current_scene_id == "shared_target"
    assert restored.start_scene_id == "start"
    assert restored.current_scene.text == "Both test paths arrive here."
    assert restored.player.name == "Fixture Player"
    assert restored.player.get_health() == 8
    assert restored.player.inventory.items == ["starter_item", "map"]
    assert restored.choice_resolver.completed_tests == {
        ("start", "Take the quiet path.")
    }


def test_save_to_file_writes_versioned_json_and_loads_session(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.current_scene_id = "shared_target"
    save_path = tmp_path / "save.json"

    written_path = save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_GAME_DIR)

    assert written_path == save_path
    assert json.loads(save_path.read_text(encoding="utf-8"))["version"] == 2
    assert loaded.current_scene_id == "shared_target"


def test_slot_helpers_use_separate_save_files(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()

    slot_path = save_to_slot(session, tmp_path, 2)
    loaded = load_from_slot(tmp_path, 2, FIXTURE_GAME_DIR)

    assert slot_path == get_slot_path(tmp_path, 2)
    assert slot_path.name == "slot_2.json"
    assert loaded.current_scene_id == "start"


def test_scene_view_includes_system_options(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.save_dir = tmp_path

    scene_view = session.get_scene_view()

    assert SHORT_REST_CHOICE_TEXT in scene_view.choices
    assert LONG_REST_CHOICE_TEXT in scene_view.choices
    assert scene_view.choices[-3:] == [
        SAVE_CHOICE_TEXT,
        LOAD_CHOICE_TEXT,
        EXIT_CHOICE_TEXT,
    ]


def test_long_rest_button_restores_health_outside_combat() -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.player.take_damage(4)

    scene_view = session.get_scene_view()
    long_rest_index = scene_view.choices.index(LONG_REST_CHOICE_TEXT)
    result = session.choose(long_rest_index)

    assert result.selected_choice_text == LONG_REST_CHOICE_TEXT
    assert ("system", "You take a long rest.") in result.messages
    assert ("system", "You recover 4 hit point(s).") in result.messages
    assert session.player.get_health() == session.player.get_max_health()


def test_short_rest_restores_one_second_wind_use() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.player.feature_uses_remaining["second_wind"] = 0

    scene_view = session.get_scene_view()
    short_rest_index = scene_view.choices.index(SHORT_REST_CHOICE_TEXT)
    result = session.choose(short_rest_index)

    assert result.selected_choice_text == SHORT_REST_CHOICE_TEXT
    assert ("system", "You take a short rest.") in result.messages
    assert ("system", "Recovered 1 feature use(s).") in result.messages
    assert session.player.feature_uses_remaining["second_wind"] == 1


def test_save_and_load_preserve_feature_uses(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.player.feature_uses_remaining["second_wind"] = 1
    save_path = tmp_path / "feature_uses_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.player.feature_uses_remaining["second_wind"] == 1


def test_session_save_choice_writes_default_slot(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.save_dir = tmp_path

    scene_view = session.get_scene_view()
    result = session.choose(len(scene_view.choices) - 3)
    slot_path = get_slot_path(tmp_path, 1)

    assert slot_path.exists()
    assert result.selected_choice_text == SAVE_CHOICE_TEXT
    assert result.next_scene_id == "start"
    assert result.scene_changed is False


def test_session_load_choice_restores_saved_state_from_default_slot(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.save_dir = tmp_path
    session.current_scene_id = "shared_target"
    session.player.take_damage(4)
    session.player.inventory.add_item("map")
    session.choice_resolver.completed_tests.add(("start", "Take the quiet path."))
    save_to_slot(session, tmp_path, 1)

    fresh_session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    fresh_session.save_dir = tmp_path
    load_choice_index = fresh_session.get_scene_view().choices.index(LOAD_CHOICE_TEXT)

    result = fresh_session.choose(load_choice_index)

    assert result.selected_choice_text == LOAD_CHOICE_TEXT
    assert fresh_session.current_scene_id == "shared_target"
    assert fresh_session.player.get_health() == 8
    assert fresh_session.player.inventory.items == ["starter_item", "map"]
    assert fresh_session.choice_resolver.completed_tests == {
        ("start", "Take the quiet path.")
    }


def test_session_load_choice_reports_missing_default_slot(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.save_dir = tmp_path
    load_choice_index = session.get_scene_view().choices.index(LOAD_CHOICE_TEXT)

    result = session.choose(load_choice_index)

    assert result.selected_choice_text == LOAD_CHOICE_TEXT
    assert result.messages == [("system", "No save file found in slot 1.")]
    assert session.current_scene_id == "start"


def test_session_exit_choice_requests_shutdown(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.save_dir = tmp_path
    exit_choice_index = session.get_scene_view().choices.index(EXIT_CHOICE_TEXT)

    result = session.choose(exit_choice_index)

    assert result.selected_choice_text == EXIT_CHOICE_TEXT
    assert result.messages == [("system", "Exiting game.")]
    assert result.should_exit is True
    assert session.current_scene_id == "start"


def test_save_validation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SaveGame.model_validate(
            {
                "version": 1,
                "current_scene_id": "start",
                "player": {
                    "actor_id": "player",
                    "current_health": 10,
                    "inventory": [],
                    "equipment": {},
                    "attributes": {
                        "base_health": 10,
                        "level": 1,
                        "strength": 10,
                        "dexterity": 10,
                        "constitution": 10,
                        "wisdom": 10,
                        "intelligence": 10,
                        "charisma": 10,
                        "base_armor_class": 10,
                    },
                },
                "unexpected": True,
            }
        )
