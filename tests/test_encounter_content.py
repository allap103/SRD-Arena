import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
    load_subclass_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    load_bestiary_catalog,
    load_creature,
    load_player_character_templates,
)
from srd_arena.content.encounters import EncounterDefinitionSchema
from srd_arena.content.spells import load_spell_catalog
from srd_arena.frontends.shared.config import load_encounter_presentation_config
from srd_arena.infrastructure.scenarios import load_scenario
from srd_arena.domain.creatures import AttackActionDefinition

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
GOBLIN_SKIRMISH_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)


@pytest.fixture(scope="module")
def creature_content() -> SimpleNamespace:
    return SimpleNamespace(
        bestiary=load_bestiary_catalog(SYSTEM_CONTENT_ROOT),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
        player_characters=load_player_character_templates(
            FIXTURE_ENCOUNTER_DIR / "player_characters"
        ),
        optional_features=load_optional_feature_catalog(SYSTEM_CONTENT_ROOT),
        subclasses=load_subclass_catalog(SYSTEM_CONTENT_ROOT),
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )


def test_load_encounter_parses_definition() -> None:
    scenario = load_scenario(str(FIXTURE_ENCOUNTER_DIR))
    encounter = scenario.encounters["goblin_encounter"]

    assert encounter.id == "goblin_encounter"
    assert encounter.grid.width == 13
    assert encounter.grid.height == 13
    assert encounter.participants[0].start.x == 1
    assert encounter.participants[0].start.y == 6
    assert len(encounter.participants) == 4
    assert [participant.creature_id for participant in encounter.participants[1:]] == [
        "goblin_1",
        "goblin_2",
        "goblin_3",
    ]
    assert encounter.participants[1].behavior.type == "chase"
    assert encounter.participants[2].behavior.anchor is not None
    assert encounter.participants[2].behavior.radius == 2
    assert len(encounter.participants[3].behavior.path) == 3
    assert encounter.victory.next_encounter_id == "goblin_encounter"
    assert encounter.defeat.next_encounter_id == "goblin_encounter"


def test_encounter_creature_can_override_team_controller(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "mixed_control"
    (scenario_dir / "encounters").mkdir(parents=True)
    (scenario_dir / "player_characters").mkdir()
    (scenario_dir / "player_characters" / "player").write_text(
        (FIXTURE_ENCOUNTER_DIR / "player_characters" / "player").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    encounter_data = json.loads(
        (FIXTURE_ENCOUNTER_DIR / "encounters" / "goblin_encounter").read_text(
            encoding="utf-8"
        )
    )
    encounter_data["creatures"][1]["controller"] = "external"
    encounter_data["creatures"][1].pop("behavior")
    (scenario_dir / "encounters" / "goblin_encounter").write_text(
        json.dumps(encounter_data),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_dir)
    participant = scenario.encounters["goblin_encounter"].participants[1]
    session = scenario.create_session()
    session.get_scene_view()

    assert participant.creature_id == "goblin_1"
    assert participant.controller == "external"
    assert session.encounter_state is not None


def test_full_control_showcase_gives_external_control_to_every_creature() -> None:
    scenario = load_scenario(GOBLIN_SKIRMISH_DIR)
    encounter = scenario.encounters["full_control_showcase"]
    session = scenario.create_session()
    session.get_scene_view()

    assert {creature.name for creature in scenario.creatures} == {
        "Aldren",
        "Brynn",
        "Redblade",
        "Redeye",
        "Blueblade",
        "Blueeye",
    }
    assert scenario.get_creature("player").subclass_ref is not None
    assert scenario.get_creature("champion_2").subclass_ref is not None
    assert scenario.get_creature("champion_2").subclass_ref.name == "Champion"
    assert all(
        participant.controller == "external" for participant in encounter.participants
    )
    assert all(team.controller == "external" for team in encounter.teams)
    assert session.encounter_state is not None
    assert all(
        session.encounter_state._creature_controller(creature_ref) == "external"
        for creature_ref in session.encounter_state.initiative_order
    )


def test_encounter_can_be_fully_scripted() -> None:
    scenario = load_scenario(str(FIXTURE_ENCOUNTER_DIR))
    encounter = scenario.encounters["goblin_encounter"]
    for team in encounter.teams:
        team.controller = "scripted"

    session = scenario.create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.encounter_state.requires_automatic_advance() is True
    assert all(
        session.encounter_state._creature_controller(creature_ref) == "scripted"
        for creature_ref in session.encounter_state.initiative_order
    )


def test_nested_creature_can_reference_system_stat_block() -> None:
    scenario = load_scenario(str(FIXTURE_ENCOUNTER_DIR))
    creature = scenario.get_creature("goblin_1")

    assert creature.id == "goblin_1"
    assert creature.name == "Goblin Warrior"
    assert creature.get_max_health() == 10
    assert creature.get_armor_class() == 15
    assert creature.attributes.strength == 8
    assert creature.attributes.dexterity == 15
    assert creature.attributes.movement.speed_feet == 30
    attacks = [
        action
        for action in creature.stat_block_actions.values()
        if isinstance(action, AttackActionDefinition)
    ]
    assert [attack.name for attack in attacks] == ["Scimitar", "Shortbow"]
    assert attacks[0].attack_modes == ("melee",)
    assert attacks[1].attack_modes == ("ranged",)
    assert attacks[1].range_normal_feet == 80
    assert creature.token_image == "tokens/goblin.png"


def test_game_uses_first_encounter_from_settings_when_not_overridden(
    tmp_path: Path,
) -> None:
    scenario_dir = tmp_path / "encounter_start"
    for subdir in ("encounters", "player_characters"):
        (scenario_dir / subdir).mkdir(parents=True, exist_ok=True)
    (scenario_dir / "config.json").write_text(
        '{"display_name": "Two Arenas", "encounters": ["arena", "arena_two"]}\n',
        encoding="utf-8",
    )
    (scenario_dir / "player_characters" / "player").write_text(
        (FIXTURE_ENCOUNTER_DIR / "player_characters" / "player").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (scenario_dir / "encounters" / "arena").write_text(
        (FIXTURE_ENCOUNTER_DIR / "encounters" / "goblin_encounter")
        .read_text(encoding="utf-8")
        .replace(
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

    scenario = load_scenario(str(scenario_dir))

    assert scenario.start_scene == "arena"
    assert scenario.encounter_order == ("arena", "arena_two")
    assert scenario.encounters["arena"].victory.next_encounter_id == "arena_two"
    assert scenario.encounters["arena_two"].victory.next_encounter_id == "arena_two"


def test_game_loads_geometry_settings_from_config_json() -> None:
    scenario = load_scenario(str(TACTICAL_SCENARIO_DIR))
    presentation = load_encounter_presentation_config(TACTICAL_SCENARIO_DIR)

    assert scenario.display_name == "Tactical Test Game"
    assert scenario.geometry_config.directional_area_cell_coverage_threshold == 0.1
    assert presentation.background_image == "maps/tactical-test.png"
    assert presentation.grid_color == "#8fa3ad"
    assert presentation.grid_opacity == 0.65

    session = scenario.create_session()
    session.get_scene_view()

    assert not hasattr(session, "background_image")
    assert not hasattr(session, "grid_color")
    assert not hasattr(session, "grid_opacity")


def test_game_uses_default_board_presentation_settings() -> None:
    presentation = load_encounter_presentation_config(FIXTURE_ENCOUNTER_DIR)

    assert presentation.background_image is None
    assert presentation.grid_color == "#d3d3d3"
    assert presentation.grid_opacity == 1.0


def test_encounter_schema_rejects_more_than_five_teams() -> None:
    with pytest.raises(ValidationError):
        EncounterDefinitionSchema.model_validate(
            {
                "id": "too_many_teams",
                "grid": {"width": 1, "height": 1},
                "teams": [
                    {
                        "id": f"team_{index}",
                        "name": "Team",
                        "controller": "scripted",
                    }
                    for index in range(6)
                ],
            }
        )


def test_encounter_schema_rejects_duplicate_creature_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="Encounter creature IDs must be unique: duplicate",
    ):
        EncounterDefinitionSchema.model_validate(
            {
                "id": "duplicate_creatures",
                "grid": {"width": 1, "height": 1},
                "creatures": [
                    {
                        "id": "duplicate",
                        "name": "First",
                        "start": {"x": 0, "y": 0},
                        "team_id": "team",
                    },
                    {
                        "id": "duplicate",
                        "name": "Second",
                        "start": {"x": 0, "y": 0},
                        "team_id": "team",
                    },
                ],
            }
        )


def test_fighter_level_five_resolves_extra_attack(
    tmp_path: Path,
    creature_content: SimpleNamespace,
) -> None:
    creature_path = tmp_path / "fighter_level_five.json"
    creature_path.write_text(
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
        creature_path,
        creature_content.bestiary,
        creature_content.classes,
        creature_content.player_characters,
    )

    assert any(
        class_feature.id == "extra_attack" for class_feature in upgraded.class_features
    )
    assert upgraded.combat_profile.attacks_per_attack_action == 2


def test_creature_can_load_subclass_and_explicit_spellcasting(
    tmp_path: Path,
    creature_content: SimpleNamespace,
) -> None:
    creature_path = tmp_path / "arcane_champion.json"
    creature_path.write_text(
        json.dumps(
            {
                "id": "arcane_champion",
                "name": "Arcane Veteran",
                "class_ref": {"name": "Fighter", "source": "XPHB"},
                "subclass_ref": {
                    "name": "Champion",
                    "source": "XPHB",
                    "class_name": "Fighter",
                    "class_source": "XPHB",
                },
                "spellcasting": {
                    "ability": "int",
                    "caster_progression": "1/3",
                    "cantrips_known": 2,
                    "spell_count": 4,
                    "spell_slots": {"1": 3},
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
        creature_path,
        creature_content.bestiary,
        creature_content.classes,
        creature_content.player_characters,
        creature_content.optional_features,
        creature_content.subclasses,
        creature_content.spells,
    )

    assert creature.subclass_ref is not None
    assert creature.subclass_ref.name == "Champion"
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
    assert creature.spellcasting.learned_spells[1].geometry_mode == "point_target"


def test_loaded_spells_classify_geometry_modes_from_game_data(
    tmp_path: Path,
    creature_content: SimpleNamespace,
) -> None:
    creature_path = tmp_path / "geometry_spells.json"
    creature_path.write_text(
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
        creature_path,
        creature_content.bestiary,
        creature_content.classes,
        creature_content.player_characters,
        creature_content.optional_features,
        creature_content.subclasses,
        creature_content.spells,
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
