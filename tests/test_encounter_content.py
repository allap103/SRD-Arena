import json
from pathlib import Path

from game.runtime.game import Game
from game.content.loaders import load_actor, load_bestiary_stat_blocks, load_scene
from game.runtime.save import load_from_file, save_to_file

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
SAMPLE_GAME_DIR = Path(__file__).parents[1] / "app" / "content" / "scenarios" / "sample_game"


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
    stat_blocks = load_bestiary_stat_blocks("app/content/system")

    actor = load_actor(FIXTURE_ENCOUNTER_DIR / "actors" / "goblin_1", stat_blocks)

    assert actor.id == "goblin_1"
    assert actor.name == "Goblin"
    assert actor.get_max_health() == 7
    assert actor.get_armor_class() == 15
    assert actor.attributes.strength == 8
    assert actor.attributes.dexterity == 14
    assert actor.attributes.movement.speed_feet == 30
    assert [attack.name for attack in actor.monster_attacks] == ["Scimitar", "Shortbow"]
    assert actor.monster_attacks[0].attack_modes == ("melee",)
    assert actor.monster_attacks[1].attack_modes == ("ranged",)
    assert actor.monster_attacks[1].range_normal == 80


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
    assert player.attributes.proficiencies["saving_throws"] == [
        "strength",
        "constitution",
    ]
    assert player.combat_profile.attacks_per_attack_action == 1
    assert "second_wind" in {grant.id for grant in player.feature_grants}
    second_wind = next(grant for grant in player.feature_grants if grant.id == "second_wind")
    assert second_wind.data["healing_die_count"] == 1
    assert second_wind.data["healing_die_sides"] == 10
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


def test_game_loads_rule_settings_from_settings_json() -> None:
    game = Game(str(SAMPLE_GAME_DIR))

    assert game.rules_config.directional_aoe_cell_coverage_threshold == 0.1


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


def test_actor_can_load_subclass_and_spellcasting_from_game_data(tmp_path: Path) -> None:
    game = Game(str(FIXTURE_ENCOUNTER_DIR))
    actor_path = tmp_path / "eldritch_knight.json"
    actor_path.write_text(
        json.dumps(
            {
                "id": "eldritch_knight",
                "name": "Arcane Veteran",
                "class_ref": {"name": "Fighter", "source": "XPHB"},
                "subclass_ref": {
                    "name": "Eldritch Knight",
                    "source": "XPHB",
                    "class_name": "Fighter",
                    "class_source": "XPHB",
                },
                "spells_known": [
                    {"name": "Color Spray", "source": "XPHB"},
                    {"name": "Lesser Restoration", "source": "XPHB"},
                ],
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
    actor = load_actor(
        actor_path,
        game.stat_blocks,
        game.class_blocks,
        game.custom_stat_blocks,
        game.optional_feature_blocks,
        game.subclass_blocks,
        game.spell_catalog,
    )

    assert actor.subclass_ref is not None
    assert actor.subclass_ref.name == "Eldritch Knight"
    assert actor.spellcasting is not None
    assert actor.spellcasting.ability == "int"
    assert actor.spellcasting.ability_modifier == 1
    assert actor.spellcasting.save_dc == 12
    assert actor.spellcasting.attack_bonus == 4
    assert actor.spellcasting.preparation_mode == "fixed"
    assert actor.spellcasting.cantrips_known == 2
    assert actor.spellcasting.spell_count == 4
    assert actor.spellcasting.spell_slots_max == {1: 3}
    assert actor.spellcasting.spell_slots_remaining == {1: 3}
    assert [spell.name for spell in actor.spellcasting.learned_spells] == [
        "Color Spray",
        "Lesser Restoration",
    ]
    assert actor.spellcasting.learned_spells[0].level == 1
    assert actor.spellcasting.learned_spells[0].condition_inflict == ("blinded",)
    assert actor.spellcasting.learned_spells[0].area_tags == ("N",)
    assert actor.spellcasting.learned_spells[0].geometry_mode == "directional_area"
    assert actor.spellcasting.learned_spells[1].level == 2
    assert actor.spellcasting.learned_spells[1].removable_conditions == (
        "blinded",
        "deafened",
        "paralyzed",
        "poisoned",
    )
    assert actor.spellcasting.learned_spells[1].geometry_mode == "self_only"


def test_loaded_spells_classify_geometry_modes_from_game_data(tmp_path: Path) -> None:
    game = Game(str(FIXTURE_ENCOUNTER_DIR))
    actor_path = tmp_path / "geometry_spells.json"
    actor_path.write_text(
        json.dumps(
            {
                "id": "geometry_spells",
                "name": "Arcane Tester",
                "class_ref": {"name": "Wizard", "source": "XPHB"},
                "spells_known": [
                    {"name": "Burning Hands", "source": "XPHB"},
                    {"name": "Thunderwave", "source": "XPHB"},
                    {"name": "Lightning Bolt", "source": "XPHB"},
                    {"name": "Fireball", "source": "XPHB"},
                ],
                "attributes": {
                    "level": 5,
                    "strength": 8,
                    "dexterity": 14,
                    "constitution": 12,
                    "wisdom": 10,
                    "intelligence": 16,
                    "charisma": 10,
                    "base_health": 12,
                    "base_armor_class": 12,
                },
            }
        ),
        encoding="utf-8",
    )
    actor = load_actor(
        actor_path,
        game.stat_blocks,
        game.class_blocks,
        game.custom_stat_blocks,
        game.optional_feature_blocks,
        game.subclass_blocks,
        game.spell_catalog,
    )

    assert actor.spellcasting is not None
    spells = {spell.name: spell for spell in actor.spellcasting.learned_spells}

    assert spells["Burning Hands"].geometry_mode == "directional_area"
    assert spells["Burning Hands"].area_tags == ("N",)
    assert spells["Burning Hands"].saving_throw_abilities == ("dexterity",)
    assert spells["Burning Hands"].damage_dice == "3d6"
    assert spells["Burning Hands"].damage_inflict == ("fire",)
    assert spells["Thunderwave"].geometry_mode == "directional_area"
    assert spells["Thunderwave"].area_tags == ("C",)
    assert spells["Lightning Bolt"].geometry_mode == "directional_area"
    assert spells["Lightning Bolt"].area_tags == ("L",)
    assert spells["Fireball"].geometry_mode == "point_area"


def test_save_and_load_preserve_spell_slots(tmp_path: Path) -> None:
    session = Game("app/content/scenarios/sample_game").create_session()

    assert session.player.spellcasting is not None
    session.player.spellcasting.spell_slots_remaining[1] = 1
    save_path = tmp_path / "spell_slots_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, "app/content/scenarios/sample_game")

    assert loaded.player.spellcasting is not None
    assert loaded.player.spellcasting.spell_slots_max == {1: 3}
    assert loaded.player.spellcasting.spell_slots_remaining == {1: 1}
