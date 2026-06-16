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

FIXTURE_GAME_DIR = Path(__file__).parent / "fixtures" / "graph_game"


def test_create_save_captures_mutable_session_state() -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()
    session.current_scene_id = "shared_target"
    session.player.take_damage(3)
    session.player.inventory.add_item("found_key")
    session.player.equipment.equip("found_key", "left_hand")
    session.choice_resolver.completed_tests.add(("start", "Take the bright path."))

    save = create_save(session)

    assert save.version == 1
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
    assert json.loads(save_path.read_text(encoding="utf-8"))["version"] == 1
    assert loaded.current_scene_id == "shared_target"


def test_slot_helpers_use_separate_save_files(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_GAME_DIR), start_scene="start").create_session()

    slot_path = save_to_slot(session, tmp_path, 2)
    loaded = load_from_slot(tmp_path, 2, FIXTURE_GAME_DIR)

    assert slot_path == get_slot_path(tmp_path, 2)
    assert slot_path.name == "slot_2.json"
    assert loaded.current_scene_id == "start"


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
