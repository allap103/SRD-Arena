import json
from pathlib import Path

from srd_arena.content.loaders import load_creature
from srd_arena.runtime.save import load_from_file, save_to_file
from srd_arena.runtime.scenario import Scenario

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
SAMPLE_SCENARIO_DIR = Path(__file__).parents[1] / "content" / "scenarios" / "sample_game"


def test_load_encounter_parses_definition() -> None:
    scenario = Scenario(str(FIXTURE_ENCOUNTER_DIR))
    scene = scenario.scenes["goblin_encounter"]

    assert scene.id == "goblin_encounter"
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
    assert scene.encounter.victory.next_scene == "goblin_encounter"
    assert scene.encounter.victory.message == (
        "The last goblin falls. You catch your breath before moving on."
    )
    assert scene.encounter.defeat.next_scene == "goblin_encounter"
    assert scene.encounter.flee is not None
    assert scene.encounter.flee.allowed is True
    assert scene.encounter.flee.next_scene == "goblin_encounter"


def test_nested_creature_can_reference_system_stat_block() -> None:
    scenario = Scenario(str(FIXTURE_ENCOUNTER_DIR))
    creature = scenario.get_creature("goblin_1")

    assert creature.id == "goblin_1"
    assert creature.name == "Goblin Warrior"
    assert creature.get_max_health() == 10
    assert creature.get_armor_class() == 15
    assert creature.attributes.strength == 8
    assert creature.attributes.dexterity == 15
    assert creature.attributes.movement.speed_feet == 30
    assert [attack.name for attack in creature.monster_attacks] == ["Scimitar", "Shortbow"]
    assert creature.monster_attacks[0].attack_modes == ("melee",)
    assert creature.monster_attacks[1].attack_modes == ("ranged",)
    assert creature.monster_attacks[1].range_normal == 80
    assert creature.token_image == "tokens/goblin.png"


def test_game_uses_first_encounter_from_settings_when_not_overridden(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "encounter_start"
    for subdir in ("encounters", "player_characters"):
        (scenario_dir / subdir).mkdir(parents=True, exist_ok=True)
    (scenario_dir / "settings.json").write_text(
        '{"encounters": ["arena", "arena_two"]}\n', encoding="utf-8"
    )
    (scenario_dir / "player_characters" / "player").write_text(
        (FIXTURE_ENCOUNTER_DIR / "player_characters" / "player").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (scenario_dir / "encounters" / "arena").write_text(
        (FIXTURE_ENCOUNTER_DIR / "encounters" / "goblin_encounter").read_text(encoding="utf-8").replace(
            '"id":  "goblin_encounter"',
            '"id":  "arena"',
        ),
        encoding="utf-8",
    )
    (scenario_dir / "encounters" / "arena_two").write_text(
        (FIXTURE_ENCOUNTER_DIR / "encounters" / "goblin_encounter")
        .read_text(encoding="utf-8")
        .replace('"id":  "goblin_encounter"', '"id":  "arena_two"'),
        encoding="utf-8",
    )

    scenario = Scenario(str(scenario_dir))

    assert scenario.start_scene == "arena"
    assert scenario.encounter_order == ("arena", "arena_two")
    assert scenario.scenes["arena"].encounter.victory.next_scene == "arena_two"
    assert scenario.scenes["arena_two"].encounter.victory.next_scene == "arena_two"


def test_game_loads_rule_settings_from_settings_json() -> None:
    scenario = Scenario(str(SAMPLE_SCENARIO_DIR))

    assert scenario.rules_config.directional_aoe_cell_coverage_threshold == 0.1


def test_fighter_level_five_resolves_extra_attack(tmp_path: Path) -> None:
    scenario = Scenario(str(FIXTURE_ENCOUNTER_DIR))
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
    upgraded = load_creature(
        actor_path,
        scenario.stat_blocks,
        scenario.class_blocks,
        scenario.player_characters,
    )

    assert any(grant.id == "extra_attack" for grant in upgraded.feature_grants)
    assert upgraded.combat_profile.attacks_per_attack_action == 2


def test_creature_can_load_subclass_and_spellcasting_from_game_data(tmp_path: Path) -> None:
    scenario = Scenario(str(FIXTURE_ENCOUNTER_DIR))
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
    creature = load_creature(
        actor_path,
        scenario.stat_blocks,
        scenario.class_blocks,
        scenario.player_characters,
        scenario.optional_feature_blocks,
        scenario.subclass_blocks,
        scenario.spell_catalog,
    )

    assert creature.subclass_ref is not None
    assert creature.subclass_ref.name == "Eldritch Knight"
    assert creature.spellcasting is not None
    assert creature.spellcasting.ability == "int"
    assert creature.spellcasting.ability_modifier == 1
    assert creature.spellcasting.save_dc == 12
    assert creature.spellcasting.attack_bonus == 4
    assert creature.spellcasting.preparation_mode == "fixed"
    assert creature.spellcasting.cantrips_known == 2
    assert creature.spellcasting.spell_count == 4
    assert creature.spellcasting.spell_slots_max == {1: 3}
    assert creature.spellcasting.spell_slots_remaining == {1: 3}
    assert [spell.name for spell in creature.spellcasting.learned_spells] == [
        "Color Spray",
        "Lesser Restoration",
    ]
    assert creature.spellcasting.learned_spells[0].level == 1
    assert creature.spellcasting.learned_spells[0].condition_inflict == ("blinded",)
    assert creature.spellcasting.learned_spells[0].area_tags == ("N",)
    assert creature.spellcasting.learned_spells[0].geometry_mode == "directional_area"
    assert creature.spellcasting.learned_spells[1].level == 2
    assert creature.spellcasting.learned_spells[1].removable_conditions == (
        "blinded",
        "deafened",
        "paralyzed",
        "poisoned",
    )
    assert creature.spellcasting.learned_spells[1].geometry_mode == "self_only"


def test_loaded_spells_classify_geometry_modes_from_game_data(tmp_path: Path) -> None:
    scenario = Scenario(str(FIXTURE_ENCOUNTER_DIR))
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
    creature = load_creature(
        actor_path,
        scenario.stat_blocks,
        scenario.class_blocks,
        scenario.player_characters,
        scenario.optional_feature_blocks,
        scenario.subclass_blocks,
        scenario.spell_catalog,
    )

    assert creature.spellcasting is not None
    spells = {spell.name: spell for spell in creature.spellcasting.learned_spells}

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
    assert spells["Fireball"].area_size_feet == 20
    assert spells["Fireball"].saving_throw_abilities == ("dexterity",)
    assert spells["Fireball"].damage_dice == "8d6"
    assert spells["Fireball"].damage_inflict == ("fire",)


def test_save_and_load_preserve_spell_slots(tmp_path: Path) -> None:
    session = Scenario("content/scenarios/sample_game").create_session()

    assert session.player.spellcasting is not None
    session.player.spellcasting.spell_slots_remaining[1] = 1
    save_path = tmp_path / "spell_slots_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, "content/scenarios/sample_game")

    assert loaded.player.spellcasting is not None
    assert loaded.player.spellcasting.spell_slots_max == {1: 4, 2: 3, 3: 2}
    assert loaded.player.spellcasting.spell_slots_remaining == {1: 1, 2: 3, 3: 2}
