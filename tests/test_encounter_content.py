import json
from pathlib import Path

from game.engine import Game
from game.loaders import load_actor, load_bestiary_stat_blocks, load_scene

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def test_load_scene_parses_optional_encounter_block() -> None:
    scene_path = FIXTURE_ENCOUNTER_DIR / "scenes" / "goblin_encounter"

    scene = load_scene(scene_path)

    assert scene.id == "goblin_encounter"
    assert scene.type == "encounter"
    assert scene.encounter is not None
    assert scene.encounter.grid.width == 13
    assert scene.encounter.grid.height == 13
    assert scene.encounter.player_start.x == 1
    assert scene.encounter.player_start.y == 6
    assert len(scene.encounter.enemies) == 3
    assert [enemy.actor_id for enemy in scene.encounter.enemies] == [
        "goblin_1",
        "goblin_2",
        "goblin_3",
    ]
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


def test_load_actor_can_reference_system_stat_block() -> None:
    stat_blocks = load_bestiary_stat_blocks("game_system")

    actor = load_actor(FIXTURE_ENCOUNTER_DIR / "actors" / "goblin_1", stat_blocks)

    assert actor.id == "goblin_1"
    assert actor.name == "Goblin"
    assert actor.get_max_health() == 7
    assert actor.get_armor_class() == 15
    assert actor.attributes.strength == 8
    assert actor.attributes.dexterity == 14
    assert actor.attributes.movement.speed_feet == 30


def test_game_loads_custom_stat_blocks_and_actor_instances() -> None:
    game = Game(str(FIXTURE_ENCOUNTER_DIR))

    actor_ids = {actor.id for actor in game.actors}
    player = game.get_actor("player")
    items_by_id = {item.id: item for item in game.items}

    assert "player" in actor_ids
    assert len([actor for actor in game.actors if actor.id == "player"]) == 1
    assert {"goblin_1", "goblin_2", "goblin_3"}.issubset(actor_ids)
    assert player.name == "Traveler"
    assert player.class_ref is not None
    assert player.class_ref.name == "Fighter"
    assert player.class_ref.source == "XPHB"
    assert player.attributes.level == 2
    assert player.attributes.proficiency_bonus == 2
    assert player.attributes.proficiencies["weapons"] == ["simple", "martial"]
    assert player.combat_profile.attacks_per_attack_action == 1
    assert "second_wind" in {grant.id for grant in player.feature_grants}
    assert "second_wind" in player.combat_profile.bonus_action_options
    assert player.combat_profile.feature_uses_max["second_wind"] == 2
    assert player.combat_profile.feature_recharge["second_wind"]["short_rest"] == 1
    assert player.combat_profile.feature_recharge["second_wind"]["long_rest"] == "all"
    assert player.feature_uses_remaining["second_wind"] == 2
    assert player.get_max_health() == 20
    assert player.get_armor_class() == 16
    assert player.inventory.items == ["potion_of_healing"]
    assert player.equipment.equipped_items["right_hand"] == "longsword"
    assert player.equipment.equipped_items["body"] == "chain_mail"
    assert items_by_id["longsword"].name == "Longsword"
    assert items_by_id["longsword"].weapon_stat is not None
    assert items_by_id["longsword"].weapon_stat.weapon_category == "martial"
    assert items_by_id["chain_mail"].name == "Chain Mail"
    assert items_by_id["potion_of_healing"].name == "Potion of Healing"
    assert items_by_id["dagger"].weapon_stat is not None
    assert items_by_id["dagger"].weapon_stat.damage == "1d4"
    assert items_by_id["shortsword"].weapon_stat is not None
    assert items_by_id["shortsword"].weapon_stat.damage == "1d6"
    assert items_by_id["chain_mail"].armor_stat is not None
    assert items_by_id["chain_mail"].armor_stat.armor_class == 16


def test_fighter_level_five_resolves_extra_attack(tmp_path: Path) -> None:
    game = Game(str(FIXTURE_ENCOUNTER_DIR))
    actor_path = tmp_path / "fighter_level_five.json"
    actor_path.write_text(
        json.dumps(
            {
                "id": "fighter_level_five",
                "name": "Veteran",
                "class_ref": {"name": "Fighter", "source": "XPHB"},
                "attributes": {
                    "level": 5,
                    "strength": 16,
                    "dexterity": 12,
                    "constitution": 14,
                    "wisdom": 8,
                    "intelligence": 12,
                    "charisma": 10,
                    "base_health": 16,
                    "base_armor_class": 15,
                },
            }
        ),
        encoding="utf-8",
    )
    upgraded = load_actor(
        actor_path,
        game.stat_blocks,
        game.class_blocks,
        game.custom_stat_blocks,
    )

    assert any(grant.id == "extra_attack" for grant in upgraded.feature_grants)
    assert upgraded.combat_profile.attacks_per_attack_action == 2
