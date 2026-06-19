from pathlib import Path

from game.loaders import load_scene


def test_load_scene_parses_optional_encounter_block() -> None:
    scene_path = Path("sample_game/scenes/goblin_encounter")

    scene = load_scene(scene_path)

    assert scene.id == "goblin_encounter"
    assert scene.type == "encounter"
    assert scene.encounter is not None
    assert scene.encounter.grid.width == 13
    assert scene.encounter.grid.height == 13
    assert scene.encounter.player_start.x == 1
    assert scene.encounter.player_start.y == 6
    assert len(scene.encounter.enemies) == 3
    assert scene.encounter.enemies[0].behavior.type == "chase"
    assert scene.encounter.enemies[1].behavior.anchor is not None
    assert scene.encounter.enemies[1].behavior.radius == 2
    assert len(scene.encounter.enemies[2].behavior.path) == 3
    assert scene.encounter.victory is not None
    assert scene.encounter.victory.next_scene == "goblin_encounter_victory"
    assert scene.encounter.defeat is not None
    assert scene.encounter.defeat.next_scene == "goblin_encounter_defeat"
    assert scene.encounter.flee is not None
    assert scene.encounter.flee.allowed is True
    assert scene.encounter.flee.next_scene == "welcome"
