"""Verify weapon-mastery identity from character content to attack runtime."""

from dataclasses import replace

from srd_arena.content.character_options.classes import load_class_catalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.equipment import load_system_items
from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters.actions.attack_resolution import (
    resolve_attack,
    weapon_attack_source,
)
from srd_arena.domain.equipment import Item


def _barbarian() -> tuple[Creature, dict[str, Item]]:
    """Build the canonical level-one Barbarian and its item lookup."""

    snapshots = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    creature = build_creature(
        snapshots.creature_template("barbarian", 1),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
    )
    items = {item.id: item for item in load_system_items(SYSTEM_CONTENT_ROOT)}
    return creature, items


def test_weapon_mastery_feature_and_selection_resolve_maul_and_javelin() -> None:
    """Require class progression, character selection, and weapon metadata."""

    barbarian, items = _barbarian()

    maul = weapon_attack_source(barbarian, items["maul"])
    barbarian.equipment = replace(
        barbarian.equipment,
        right_hand=None,
        left_hand="javelin",
    )
    javelin = weapon_attack_source(barbarian, items["javelin"])

    assert any(feature.id == "weapon_mastery" for feature in barbarian.class_features)
    assert maul.weapon_mastery == "Topple"
    assert javelin.weapon_mastery == "Slow"


def test_weapon_mastery_requires_the_weapon_to_be_selected() -> None:
    """Do not unlock a weapon property merely because the item carries it."""

    barbarian, items = _barbarian()
    assert barbarian.character_profile is not None
    barbarian.character_profile = replace(
        barbarian.character_profile,
        weapon_masteries=("Javelin",),
    )

    source = weapon_attack_source(barbarian, items["maul"])

    assert source.weapon_mastery is None


def test_attack_outcome_exposes_resolved_mastery_even_on_a_miss() -> None:
    """Preserve mastery context for future hit- and miss-triggered properties."""

    barbarian, items = _barbarian()
    target = build_creature(CreatureSchema(id="target", name="Target"))

    outcome = resolve_attack(
        barbarian,
        target,
        "Barbarian",
        "Target",
        d20_roller=lambda sides: 1,
        die_roller=lambda sides: 1,
        items_by_id=items,
        preferred_attack_name="Maul",
    )

    assert outcome.hit is False
    assert outcome.weapon_mastery == "Topple"
    assert outcome.attack_roll_detail["weapon_mastery"] == "Topple"
