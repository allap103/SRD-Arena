import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    load_bestiary_catalog,
    load_creature,
    load_player_character_templates,
)
from srd_arena.content.encounters import (
    EncounterCatalog,
    EncounterConfigSchema,
    EncounterDefinitionSchema,
    load_encounter_directory,
)
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.creatures import AttackActionDefinition
from srd_arena.domain.encounters.participants import creature_controller
from srd_arena.engine.session import Session

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
GOBLIN_SKIRMISH_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "full_control_showcase"
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
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )


def test_load_encounter_parses_definition() -> None:
    encounter = load_encounter_directory(str(FIXTURE_ENCOUNTER_DIR))

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
    chase = encounter.participants[1].behavior
    guard = encounter.participants[2].behavior
    patrol = encounter.participants[3].behavior
    assert chase is not None
    assert guard is not None
    assert patrol is not None
    assert chase.type == "chase"
    assert guard.anchor is not None
    assert guard.radius == 2
    assert len(patrol.path) == 3


def test_encounter_creature_can_override_team_controller(tmp_path: Path) -> None:
    encounter_dir = tmp_path / "mixed_control"
    encounter_dir.mkdir()
    (encounter_dir / "player_characters").mkdir()
    (encounter_dir / "player_characters" / "player").write_text(
        (FIXTURE_ENCOUNTER_DIR / "player_characters" / "player").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    encounter_data = json.loads(
        (FIXTURE_ENCOUNTER_DIR / "encounter.json").read_text(encoding="utf-8")
    )
    encounter_data["creatures"][1]["controller"] = "external"
    encounter_data["creatures"][1].pop("behavior")
    (encounter_dir / "encounter.json").write_text(
        json.dumps(encounter_data),
        encoding="utf-8",
    )

    encounter = load_encounter_directory(encounter_dir)
    participant = encounter.participants[1]
    session = Session(encounter)
    session.read()

    assert participant.creature_id == "goblin_1"
    assert participant.controller == "external"
    assert session.encounter_state is not None


def test_full_control_showcase_gives_external_control_to_every_creature() -> None:
    encounter = load_encounter_directory(GOBLIN_SKIRMISH_DIR)
    session = Session(encounter)
    session.read()

    assert {creature.name for creature in encounter.creatures} == {
        "Aldren",
        "Brynn",
        "Redblade",
        "Redeye",
        "Blueblade",
        "Blueeye",
    }
    assert all(
        participant.controller == "external" for participant in encounter.participants
    )
    assert all(team.controller == "external" for team in encounter.teams)
    assert session.encounter_state is not None
    assert all(
        creature_controller(session.encounter_state, creature_ref) == "external"
        for creature_ref in session.encounter_state.initiative_order
    )


def test_encounter_can_be_fully_scripted() -> None:
    encounter = load_encounter_directory(str(FIXTURE_ENCOUNTER_DIR))
    for team in encounter.teams:
        team.controller = "scripted"

    session = Session(encounter)
    session.read()

    assert session.encounter_state is not None
    assert session.encounter_state.requires_automatic_advance() is True
    assert all(
        creature_controller(session.encounter_state, creature_ref) == "scripted"
        for creature_ref in session.encounter_state.initiative_order
    )


def test_nested_creature_can_reference_system_stat_block() -> None:
    encounter = load_encounter_directory(str(FIXTURE_ENCOUNTER_DIR))
    creature = encounter.get_creature("goblin_1")

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


def test_encounter_config_rejects_removed_encounter_sequences() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EncounterConfigSchema.model_validate(
            {"display_name": "Two Arenas", "encounters": ["arena", "arena_two"]}
        )


def test_game_loads_geometry_settings_from_config_json() -> None:
    encounter = load_encounter_directory(str(TACTICAL_ENCOUNTER_DIR))
    presentation = next(
        summary.presentation
        for summary in EncounterCatalog(
            encounter_root=TACTICAL_ENCOUNTER_DIR.parent
        ).available_encounters()
        if summary.id == TACTICAL_ENCOUNTER_DIR.name
    )

    assert encounter.display_name == "Tactical Test Game"
    assert encounter.geometry_config.directional_area_cell_coverage_threshold == 0.1
    assert presentation.background_image == "maps/tactical-test.png"
    assert presentation.grid_color == "#8fa3ad"
    assert presentation.grid_opacity == 0.65

    session = Session(encounter)
    session.read()

    assert not hasattr(session, "background_image")
    assert not hasattr(session, "grid_color")
    assert not hasattr(session, "grid_opacity")


def test_game_uses_default_board_presentation_settings() -> None:
    presentation = next(
        summary.presentation
        for summary in EncounterCatalog(
            encounter_root=FIXTURE_ENCOUNTER_DIR.parent
        ).available_encounters()
        if summary.id == FIXTURE_ENCOUNTER_DIR.name
    )

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


def test_encounter_schema_rejects_overlapping_creature_starts() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            r"Encounter creature starting positions must be unique: "
            r"\(0, 0\): first, second"
        ),
    ):
        EncounterDefinitionSchema.model_validate(
            {
                "id": "overlapping_creatures",
                "grid": {"width": 2, "height": 2},
                "creatures": [
                    {
                        "id": "first",
                        "name": "First",
                        "start": {"x": 0, "y": 0},
                        "team_id": "team",
                    },
                    {
                        "id": "second",
                        "name": "Second",
                        "start": {"x": 0, "y": 0},
                        "team_id": "team",
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("start", "position_text"),
    [
        ({"x": -1, "y": 0}, r"\(-1, 0\)"),
        ({"x": 0, "y": -1}, r"\(0, -1\)"),
        ({"x": 2, "y": 0}, r"\(2, 0\)"),
        ({"x": 0, "y": 2}, r"\(0, 2\)"),
    ],
)
def test_encounter_schema_rejects_creature_starts_outside_grid(
    start: dict[str, int],
    position_text: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=(
            r"Encounter creature starting positions must lie within the grid: "
            rf"traveler at {position_text}"
        ),
    ):
        EncounterDefinitionSchema.model_validate(
            {
                "id": "outside_grid",
                "grid": {"width": 2, "height": 2},
                "creatures": [
                    {
                        "id": "traveler",
                        "name": "Traveler",
                        "start": start,
                        "team_id": "team",
                    }
                ],
            }
        )


@pytest.mark.parametrize(("level", "attacks"), [(5, 2), (11, 3), (20, 4)])
def test_supported_fighter_levels_resolve_extra_attack(
    tmp_path: Path,
    creature_content: SimpleNamespace,
    level: int,
    attacks: int,
) -> None:
    creature_path = tmp_path / f"fighter_level_{level}.json"
    creature_path.write_text(
        json.dumps(
            {
                "id": f"fighter_level_{level}",
                "name": "Veteran",
                "class_ref": {"name": "Fighter", "source": "XPHB"},
                "attributes": {
                    "level": level,
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
    assert upgraded.combat_profile.attacks_per_attack_action == attacks


@pytest.mark.parametrize(
    ("unsupported", "message"),
    [
        ({"equipment": {"body": "chain_mail"}}, "right_hand.*left_hand"),
        (
            {"subclass_ref": {"name": "Champion", "source": "XPHB"}},
            "Extra inputs are not permitted",
        ),
    ],
)
def test_creature_schema_rejects_deferred_player_character_systems(
    unsupported: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        CreatureSchema.model_validate({"id": "hero", **unsupported})


def test_creature_can_load_explicit_spellcasting(
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
        creature_content.spells,
    )

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
                "spellcasting": {
                    "ability": "int",
                    "caster_progression": "full",
                    "spell_slots": {"1": 4, "2": 3, "3": 2},
                },
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
