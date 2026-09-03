"""Verify recovery for the canonical characters' limited resources."""

import json
from pathlib import Path

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.creatures import RestType, Spellcasting
from srd_arena.engine.api import Session


def test_pact_magic_slots_recover_on_either_rest() -> None:
    catalog = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    warlock = build_creature(
        catalog.creature_template("warlock", 5),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
        optional_features=load_optional_feature_catalog(SYSTEM_CONTENT_ROOT),
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )
    assert warlock.spellcasting is not None

    assert warlock.spellcasting.spend_slot(3) == 1
    recoveries = warlock.recover_resources(RestType.SHORT)

    assert warlock.spellcasting.spell_slots_remaining == {3: 2}
    assert [(item.resource_id, item.amount) for item in recoveries] == [
        ("spell_slots:3", 1)
    ]

    warlock.spellcasting.spend_slot(3)
    assert warlock.recover_resources(RestType.LONG)[0].current == 2


def test_ordinary_spell_slots_require_a_long_rest() -> None:
    casting = Spellcasting(
        "wis",
        3,
        13,
        5,
        "full",
        spell_slots_max={1: 2},
        spell_slots_remaining={1: 1},
    )

    assert casting.recover_slots(RestType.SHORT) == ()
    assert casting.spell_slots_remaining == {1: 1}
    assert casting.recover_slots(RestType.LONG)[0].current == 2


def test_daily_stat_block_uses_refresh_only_at_the_explicit_daily_boundary() -> None:
    aboleth = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "aboleth",
                "stat_block": {"name": "Aboleth", "source": "XMM"},
            }
        ),
        bestiary=load_bestiary_catalog(SYSTEM_CONTENT_ROOT),
    )
    resource_id = "Dominate Mind (2/Day)"
    aboleth.stat_block_action_resources[resource_id] = 0

    assert aboleth.recover_resources(RestType.LONG) == ()
    recovery = aboleth.refresh_daily_resources()

    assert aboleth.stat_block_action_resources[resource_id] == 2
    assert [(item.resource_id, item.previous, item.current) for item in recovery] == [
        ("stat_block_action:Dominate Mind (2/Day)", 0, 2)
    ]


def test_rage_uses_follow_level_progression_and_rest_recovery() -> None:
    catalog = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)

    level_one = build_creature(
        catalog.creature_template("barbarian", 1),
        classes=classes,
    )
    level_five = build_creature(
        catalog.creature_template("barbarian", 5),
        classes=classes,
    )

    assert level_one.feature_uses_remaining["rage"] == 2
    assert level_five.feature_uses_remaining["rage"] == 3
    assert level_five.spend_feature_use("rage") == 2
    assert level_five.spend_feature_use("rage") == 1

    short_recovery = level_five.recover_resources(RestType.SHORT)
    assert level_five.feature_uses_remaining["rage"] == 2
    assert short_recovery[0].resource_id == "feature:rage"
    assert short_recovery[0].amount == 1

    level_five.spend_feature_use("rage")
    level_five.spend_feature_use("rage")
    long_recovery = level_five.recover_resources(RestType.LONG)
    assert level_five.feature_uses_remaining["rage"] == 3
    assert long_recovery[0].amount == 3


def test_rage_pool_and_recovery_are_visible_in_engine_observations(
    tmp_path: Path,
) -> None:
    encounter = {
        "id": "rage_resources",
        "grid": {"width": 5, "height": 5},
        "teams": [
            {"id": "heroes", "name": "Heroes", "controller": "external"},
            {"id": "foes", "name": "Foes", "controller": "scripted"},
        ],
        "creatures": [
            {
                "id": "barbarian",
                "character_snapshot": {"build": "barbarian", "level": 5},
                "team_id": "heroes",
                "start": {"x": 1, "y": 1},
            },
            {
                "id": "target",
                "stat_block": {"name": "Bandit", "source": "XMM"},
                "team_id": "foes",
                "start": {"x": 3, "y": 3},
            },
        ],
    }
    (tmp_path / "encounter.json").write_text(
        json.dumps(encounter),
        encoding="utf-8",
    )
    session = Session(load_encounter_directory(tmp_path), seed=7)
    observation = session.observe()
    assert observation.encounter is not None

    barbarian = next(
        creature
        for creature in observation.encounter.creatures
        if creature.creature_id == "barbarian"
    )
    rage = next(
        resource
        for resource in barbarian.resource_pools
        if resource.id == "feature:rage"
    )

    assert (rage.remaining, rage.maximum, rage.refresh) == (
        3,
        3,
        ("long_rest", "short_rest"),
    )
