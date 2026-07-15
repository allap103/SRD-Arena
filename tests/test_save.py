import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from game.domain.combat.encounter import EncounterState
from game.runtime.scenario import Scenario
from game.runtime.save import (
    SaveGame,
    create_save,
    get_slot_path,
    load_from_file,
    load_from_slot,
    restore_save,
    save_to_file,
    save_to_slot,
)
from game.runtime.session import (
    CONTINUE_CHOICE_TEXT,
    EXIT_CHOICE_TEXT,
    LOAD_CHOICE_TEXT,
    SAVE_CHOICE_TEXT,
)

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self, player):
        self.initiative_entries = []
        self.initiative_order = [
            "player",
            *(f"enemy:{index}" for index, _enemy in enumerate(self.enemies)),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def test_create_save_captures_mutable_session_state() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    starting_health = session.player.get_health()
    starting_inventory = list(session.player.inventory.items)
    session.player.take_damage(3)
    session.player.inventory.add_item("found_key")
    session.player.equipment.equip("found_key", "left_hand")

    save = create_save(session)

    assert save.version == 6
    assert save.current_scene_id == "goblin_encounter"
    assert save.start_scene_id == "goblin_encounter"
    assert save.player.actor_id == "player"
    assert save.player.current_health == starting_health - 3
    assert save.player.inventory == [*starting_inventory, "found_key"]
    assert save.player.equipment["left_hand"] == "found_key"
    assert save.encounter is not None
    assert save.encounter.scene_id == "goblin_encounter"


def test_restore_save_reloads_content_and_applies_saved_state() -> None:
    original = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    starting_health = original.player.get_health()
    player_name = original.player.name
    starting_inventory = list(original.player.inventory.items)
    original.player.take_damage(4)
    original.player.inventory.add_item("map")

    restored = restore_save(create_save(original), FIXTURE_ENCOUNTER_DIR)

    assert restored.current_scene_id == "goblin_encounter"
    assert restored.start_scene_id == "goblin_encounter"
    assert restored.current_scene.text == (
        "As you charge towards the goblins, they quickly ready their weapons and prepare "
        "to fight. The goblin with the bow takes aim at you, while the other two reach "
        "for their primitive swords. The battle begins!"
    )
    assert restored.player.name == player_name
    assert restored.player.get_health() == starting_health - 4
    assert restored.player.inventory.items == [*starting_inventory, "map"]
    assert restored.encounter_state is not None


def test_save_to_file_writes_versioned_json_and_loads_session(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    save_path = tmp_path / "save.json"

    written_path = save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert written_path == save_path
    assert json.loads(save_path.read_text(encoding="utf-8"))["version"] == 6
    assert loaded.current_scene_id == "goblin_encounter"


def test_slot_helpers_use_separate_save_files(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()

    slot_path = save_to_slot(session, tmp_path, 2)
    loaded = load_from_slot(tmp_path, 2, FIXTURE_ENCOUNTER_DIR)

    assert slot_path == get_slot_path(tmp_path, 2)
    assert slot_path.name == "slot_2.json"
    assert loaded.current_scene_id == "goblin_encounter"


def test_scene_view_includes_continue_and_system_options(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.save_dir = tmp_path
    session.current_scene_id = "welcome"

    scene_view = session.get_scene_view()

    assert scene_view.choices[0] == CONTINUE_CHOICE_TEXT
    assert scene_view.choices[-3:] == [
        SAVE_CHOICE_TEXT,
        LOAD_CHOICE_TEXT,
        EXIT_CHOICE_TEXT,
    ]


def test_save_and_load_preserve_feature_uses(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.player.feature_uses_remaining["second_wind"] = 1
    save_path = tmp_path / "feature_uses_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.player.feature_uses_remaining["second_wind"] == 1


def test_session_save_choice_writes_default_slot(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.save_dir = tmp_path

    scene_view = session.get_scene_view()
    result = session.choose(len(scene_view.choices) - 3)
    slot_path = get_slot_path(tmp_path, 1)

    assert slot_path.exists()
    assert result.selected_choice_text == SAVE_CHOICE_TEXT
    assert result.next_scene_id == "goblin_encounter"
    assert result.scene_changed is False


def test_session_load_choice_restores_saved_state_from_default_slot(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    starting_health = session.player.get_health()
    starting_inventory = list(session.player.inventory.items)
    session.save_dir = tmp_path
    session.player.take_damage(4)
    session.player.inventory.add_item("map")
    save_to_slot(session, tmp_path, 1)

    fresh_session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    fresh_session.save_dir = tmp_path
    load_choice_index = fresh_session.get_scene_view().choices.index(LOAD_CHOICE_TEXT)

    result = fresh_session.choose(load_choice_index)

    assert result.selected_choice_text == LOAD_CHOICE_TEXT
    assert fresh_session.current_scene_id == "goblin_encounter"
    assert fresh_session.player.get_health() == starting_health - 4
    assert fresh_session.player.inventory.items == [*starting_inventory, "map"]


def test_session_load_choice_reports_missing_default_slot(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.save_dir = tmp_path
    load_choice_index = session.get_scene_view().choices.index(LOAD_CHOICE_TEXT)

    result = session.choose(load_choice_index)

    assert result.selected_choice_text == LOAD_CHOICE_TEXT
    assert result.messages == [("system", "No save file found in slot 1.")]
    assert session.current_scene_id == "goblin_encounter"


def test_session_exit_choice_requests_shutdown(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.save_dir = tmp_path
    exit_choice_index = session.get_scene_view().choices.index(EXIT_CHOICE_TEXT)

    result = session.choose(exit_choice_index)

    assert result.selected_choice_text == EXIT_CHOICE_TEXT
    assert result.should_exit is True
    assert session.current_scene_id == "goblin_encounter"


def test_save_and_load_preserve_pending_scene_transition(tmp_path: Path) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    for enemy in state.enemies:
        enemy.actor.current_health = 0
    wait_index = session.get_scene_view().choices.index("Wait")
    session.choose(wait_index)

    save_path = tmp_path / "pending_transition.json"
    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.pending_scene_transition is not None
    assert CONTINUE_CHOICE_TEXT in loaded.get_scene_view().choices


def test_save_game_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SaveGame.model_validate(
            {
                "version": 6,
                "current_scene_id": "goblin_encounter",
                "player": {
                    "actor_id": "player",
                    "current_health": 12,
                    "inventory": [],
                    "equipment": {},
                    "attributes": {
                        "base_health": 10,
                        "level": 1,
                        "movement": {"speed_feet": 30, "feet_per_square": 5},
                        "strength": 16,
                        "dexterity": 12,
                        "constitution": 14,
                        "wisdom": 8,
                        "intelligence": 12,
                        "charisma": 10,
                        "base_armor_class": 10,
                    },
                },
                "bonus": "nope",
            }
        )
