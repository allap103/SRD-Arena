"""Verify the fixed Warlock and Barbarian build snapshots."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CharacterBuildSchema,
    CharacterSnapshotCatalog,
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import load_spell_catalog

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


@pytest.fixture(scope="module")
def snapshot_catalog() -> CharacterSnapshotCatalog:
    return load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)


@pytest.mark.parametrize(
    (
        "build_id",
        "level",
        "ability",
        "ability_score",
        "maximum_health",
        "armor_class",
        "speed",
    ),
    [
        ("warlock", 1, "charisma", 17, 10, 14, 30),
        ("warlock", 2, "charisma", 17, 17, 14, 30),
        ("warlock", 3, "charisma", 17, 24, 15, 30),
        ("warlock", 4, "charisma", 19, 31, 15, 30),
        ("warlock", 5, "charisma", 19, 48, 15, 30),
        ("barbarian", 1, "strength", 16, 15, 16, 30),
        ("barbarian", 2, "strength", 16, 25, 16, 30),
        ("barbarian", 3, "strength", 16, 35, 16, 30),
        ("barbarian", 4, "strength", 18, 45, 16, 30),
        ("barbarian", 5, "strength", 18, 55, 16, 40),
    ],
)
def test_canonical_snapshots_compile_expected_combat_statistics(
    snapshot_catalog: CharacterSnapshotCatalog,
    build_id: str,
    level: int,
    ability: str,
    ability_score: int,
    maximum_health: int,
    armor_class: int,
    speed: int,
) -> None:
    creature = build_creature(
        snapshot_catalog.creature_template(build_id, level),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
        optional_features=load_optional_feature_catalog(SYSTEM_CONTENT_ROOT),
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )

    assert creature.attributes.level == level
    assert getattr(creature.attributes, ability) == ability_score
    assert creature.attributes.proficiency_bonus == (3 if level == 5 else 2)
    assert creature.get_max_health() == maximum_health
    assert creature.get_armor_class() == armor_class
    assert creature.attributes.movement.speed_feet == speed


def test_warlock_snapshots_expose_pact_progression_and_selected_spells(
    snapshot_catalog: CharacterSnapshotCatalog,
) -> None:
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)
    optional_features = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    expected_slots = ({1: 1}, {1: 2}, {2: 2}, {2: 2}, {3: 2})
    expected_save_dcs = (13, 13, 13, 14, 15)
    expected_spell_ids = (
        ("eldritch_blast", "mind_sliver", "hex", "hideous_laughter"),
        (
            "eldritch_blast",
            "mind_sliver",
            "hex",
            "hideous_laughter",
            "armor_of_agathys",
        ),
        (
            "eldritch_blast",
            "mind_sliver",
            "hex",
            "hideous_laughter",
            "armor_of_agathys",
            "hold_person",
            "burning_hands",
            "command",
            "scorching_ray",
        ),
        (
            "eldritch_blast",
            "mind_sliver",
            "hex",
            "hideous_laughter",
            "armor_of_agathys",
            "hold_person",
            "misty_step",
            "burning_hands",
            "command",
            "scorching_ray",
        ),
        (
            "eldritch_blast",
            "mind_sliver",
            "hex",
            "hideous_laughter",
            "armor_of_agathys",
            "hold_person",
            "misty_step",
            "hypnotic_pattern",
            "burning_hands",
            "command",
            "scorching_ray",
            "fireball",
            "stinking_cloud",
        ),
    )
    expected_invocations = (
        ("Eldritch Mind",),
        ("Eldritch Mind", "Agonizing Blast", "Repelling Blast"),
        ("Eldritch Mind", "Agonizing Blast", "Repelling Blast"),
        ("Eldritch Mind", "Agonizing Blast", "Repelling Blast"),
        (
            "Eldritch Mind",
            "Agonizing Blast",
            "Repelling Blast",
            "Fiendish Vigor",
            "Lessons of the First Ones",
        ),
    )

    for level, slots, save_dc, spell_ids, invocations in zip(
        range(1, 6),
        expected_slots,
        expected_save_dcs,
        expected_spell_ids,
        expected_invocations,
        strict=True,
    ):
        creature = build_creature(
            snapshot_catalog.creature_template("warlock", level),
            classes=classes,
            optional_features=optional_features,
            spells=spells,
        )
        assert creature.class_ref is not None
        assert creature.class_ref.name == "Warlock"
        assert creature.spellcasting is not None
        assert creature.spellcasting.caster_progression == "pact"
        assert creature.spellcasting.spell_slots_max == slots
        assert creature.spellcasting.spell_slots_remaining == slots
        assert creature.spellcasting.save_dc == save_dc
        assert tuple(spell.id for spell in creature.spellcasting.learned_spells) == (
            spell_ids
        )
        assert creature.character_profile is not None
        assert (
            tuple(
                feature.name for feature in creature.character_profile.selected_features
            )
            == invocations
        )
        triggered_effect_ids = {effect.id for effect in creature.triggered_effects}
        assert "eldritch_mind" in triggered_effect_ids
        assert ("agonizing_blast" in triggered_effect_ids) is (level >= 2)
        assert ("repelling_blast" in triggered_effect_ids) is (level >= 2)

    level_five = build_creature(
        snapshot_catalog.creature_template("warlock", 5),
        classes=classes,
        optional_features=optional_features,
        spells=spells,
    )
    assert level_five.spellcasting is not None
    learned = {spell.id: spell for spell in level_five.spellcasting.learned_spells}
    assert {"eldritch_blast", "mind_sliver", "armor_of_agathys", "fireball"} <= set(
        learned
    )
    assert learned["mind_sliver"].definition is not None
    assert learned["armor_of_agathys"].definition is not None
    assert "suggestion" not in learned
    assert "minor_illusion" not in learned


def test_tough_bonus_is_derived_from_the_selected_feat(
    snapshot_catalog: CharacterSnapshotCatalog,
) -> None:
    """Derive the level-five Tough bonus instead of baking it into base health."""

    schema = snapshot_catalog.creature_template("warlock", 5)
    warlock = build_creature(
        schema,
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
        optional_features=load_optional_feature_catalog(SYSTEM_CONTENT_ROOT),
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )

    assert schema.attributes.base_health == 28
    assert warlock.get_max_health() == 48
    assert warlock.get_health() == 48


def test_barbarian_level_five_reuses_existing_extra_attack_support(
    snapshot_catalog: CharacterSnapshotCatalog,
) -> None:
    barbarian = build_creature(
        snapshot_catalog.creature_template("barbarian", 5),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
    )
    snapshot = snapshot_catalog.snapshot("barbarian", 5)

    assert barbarian.class_ref is not None
    assert barbarian.class_ref.name == "Barbarian"
    assert barbarian.character_profile is not None
    assert barbarian.character_profile.species.name == "Human"
    assert barbarian.character_profile.background.name == "Soldier"
    assert barbarian.character_profile.subclass is not None
    assert barbarian.character_profile.subclass.name == "Path of the Berserker"
    assert barbarian.character_profile.weapon_masteries == (
        "Maul",
        "Javelin",
        "Greatsword",
    )
    assert barbarian.combat_profile.attacks_per_attack_action == 2
    assert barbarian.skill_check_bonus("strength", "athletics") == 7
    assert barbarian.equipment.right_hand == "maul"
    assert barbarian.equipment.left_hand == "javelin"
    assert snapshot.weapon_masteries == ("Maul", "Javelin", "Greatsword")


@pytest.mark.parametrize("level", range(1, 6))
def test_barbarian_unarmored_defense_is_a_competing_ac_calculation(
    snapshot_catalog: CharacterSnapshotCatalog,
    level: int,
) -> None:
    """Derive Unarmored Defense without baking Constitution into base AC."""

    schema = snapshot_catalog.creature_template("barbarian", level)
    barbarian = build_creature(
        schema,
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
    )

    assert schema.attributes.base_armor_class == 10
    assert "unarmored_defense" in barbarian.combat_profile.armor_class_calculations
    assert barbarian.get_armor_class() == 16

    # A better standard armor calculation wins; the formulas never stack.
    barbarian.attributes.base_armor_class = 15
    assert barbarian.get_armor_class() == 18


def test_barbarian_snapshots_expose_selected_progression_at_each_level(
    snapshot_catalog: CharacterSnapshotCatalog,
) -> None:
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)
    expected_masteries = (
        ("Maul", "Javelin"),
        ("Maul", "Javelin"),
        ("Maul", "Javelin"),
        ("Maul", "Javelin", "Greatsword"),
        ("Maul", "Javelin", "Greatsword"),
    )

    for level, masteries in zip(range(1, 6), expected_masteries, strict=True):
        barbarian = build_creature(
            snapshot_catalog.creature_template("barbarian", level),
            classes=classes,
        )
        assert barbarian.character_profile is not None
        assert barbarian.character_profile.weapon_masteries == masteries
        assert tuple(feat.name for feat in barbarian.character_profile.feats) == (
            "Savage Attacker",
            "Alert",
        )
        assert (
            barbarian.character_profile.subclass.name
            if barbarian.character_profile.subclass is not None
            else None
        ) == ("Path of the Berserker" if level >= 3 else None)
        assert barbarian.combat_profile.attacks_per_attack_action == (
            2 if level == 5 else 1
        )


def test_snapshot_templates_are_independent_copies(
    snapshot_catalog: CharacterSnapshotCatalog,
) -> None:
    first = snapshot_catalog.creature_template("warlock", 1)
    second = snapshot_catalog.creature_template("warlock", 1)

    first.attributes.charisma = 1

    assert second.attributes.charisma == 17
    assert snapshot_catalog.snapshot("warlock", 1).creature.attributes.charisma == 17


def test_encounter_directory_resolves_canonical_snapshot_references(
    tmp_path: Path,
) -> None:
    encounter = {
        "id": "canonical_party",
        "grid": {"width": 8, "height": 8},
        "teams": [
            {"id": "heroes", "name": "Heroes", "controller": "external"},
            {"id": "foes", "name": "Foes", "controller": "scripted"},
        ],
        "creatures": [
            {
                "id": "learner",
                "name": "Learner",
                "character_snapshot": {"build": "warlock", "level": 5},
                "team_id": "heroes",
                "start": {"x": 1, "y": 1},
            },
            {
                "id": "ally",
                "name": "Ally",
                "character_snapshot": {"build": "barbarian", "level": 5},
                "team_id": "heroes",
                "controller": "scripted",
                "start": {"x": 2, "y": 1},
            },
            {
                "id": "target",
                "stat_block": {"name": "Bandit", "source": "XMM"},
                "team_id": "foes",
                "start": {"x": 6, "y": 6},
            },
        ],
    }
    (tmp_path / "encounter.json").write_text(
        json.dumps(encounter),
        encoding="utf-8",
    )

    definition = load_encounter_directory(tmp_path)
    learner = definition.get_creature("learner")
    ally = definition.get_creature("ally")

    assert learner.name == "Learner"
    assert learner.attributes.level == 5
    assert learner.spellcasting is not None
    assert learner.spellcasting.spell_slots_max == {3: 2}
    assert learner.character_profile is not None
    assert learner.character_profile.build_id == "warlock"
    assert tuple(feat.name for feat in learner.character_profile.feats) == (
        "Lucky",
        "Alert",
        "Tough",
    )
    assert tuple(
        feature.name for feature in learner.character_profile.selected_features
    ) == (
        "Eldritch Mind",
        "Agonizing Blast",
        "Repelling Blast",
        "Fiendish Vigor",
        "Lessons of the First Ones",
    )
    assert ally.name == "Ally"
    assert ally.attributes.level == 5
    assert ally.combat_profile.attacks_per_attack_action == 2


def test_warlock_training_scenario_uses_the_canonical_level_five_party() -> None:
    encounter = load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR)

    warlock = encounter.get_creature("warlock")
    barbarian = encounter.get_creature("barbarian")
    ogre = encounter.get_creature("ogre_target")
    assert warlock.character_profile is not None
    assert warlock.character_profile.build_id == "warlock"
    assert warlock.attributes.level == 5
    assert barbarian.character_profile is not None
    assert barbarian.character_profile.build_id == "barbarian"
    assert barbarian.attributes.level == 5
    assert ogre.size == "L"
    assert {creature.id for creature in encounter.creatures} == {
        "warlock",
        "barbarian",
        "goblin_1",
        "goblin_2",
        "goblin_3",
        "ogre_target",
    }
    controllers = {
        participant.creature_id: participant.controller
        for participant in encounter.participants
    }
    assert controllers == {
        "warlock": "external",
        "barbarian": "scripted",
        "goblin_1": None,
        "goblin_2": None,
        "goblin_3": None,
        "ogre_target": None,
    }
    assert {team.id: team.controller for team in encounter.teams} == {
        "heroes": "external",
        "goblins": "scripted",
    }
    assert (
        next(
            participant
            for participant in encounter.participants
            if participant.creature_id == "ogre_target"
        ).takes_turns
        is False
    )


def test_character_build_validation_rejects_level_gaps() -> None:
    with pytest.raises(ValidationError, match="contiguous from level 1"):
        CharacterBuildSchema.model_validate(
            {
                "id": "hero",
                "name": "Hero",
                "species": {"name": "Human"},
                "background": {"name": "Guard"},
                "class_ref": {"name": "Fighter"},
                "snapshots": [
                    {
                        "level": 2,
                        "creature": {
                            "id": "hero",
                            "attributes": {"level": 2},
                        },
                    }
                ],
            }
        )


def test_character_snapshot_validation_rejects_mismatched_levels() -> None:
    with pytest.raises(ValidationError, match="must match"):
        CharacterBuildSchema.model_validate(
            {
                "id": "hero",
                "name": "Hero",
                "species": {"name": "Human"},
                "background": {"name": "Guard"},
                "class_ref": {"name": "Fighter"},
                "snapshots": [
                    {
                        "level": 1,
                        "creature": {
                            "id": "hero",
                            "attributes": {"level": 2},
                        },
                    }
                ],
            }
        )
