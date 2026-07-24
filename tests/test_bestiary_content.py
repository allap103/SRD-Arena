from pathlib import Path

import pytest

from srd_arena.content.catalogs import SourceCatalog, load_bestiary_catalog
from srd_arena.content.loaders.creatures import build_creature
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import (
    BestiaryFileSchema,
    BestiaryMonsterSchema,
    CreatureSchema,
)
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw


def test_bundled_bestiary_loads_as_typed_records() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    goblin = catalog.find("Goblin Warrior", "xmm")

    assert len(catalog) >= 300
    assert isinstance(goblin, BestiaryMonsterSchema)
    assert goblin.armor_class == 15
    assert goblin.average_hit_points == 10
    assert goblin.walk_speed == 30
    assert [action.name for action in goblin.action] == ["Scimitar", "Shortbow"]


def test_bestiary_core_statistics_build_a_domain_creature() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    creature = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "aboleth",
                "stat_block": {"name": "Aboleth", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )

    assert creature.get_max_health() == 150
    assert creature.get_armor_class() == 17
    assert creature.attributes.proficiency_bonus == 4
    assert creature.attributes.movement.speed_feet == 10
    assert creature.attributes.movement.swim_feet == 40
    assert creature.statistics.creature_type == "aberration"
    assert creature.statistics.challenge_rating == "10"
    assert creature.statistics.saving_throw_bonuses["intelligence"] == 8
    assert creature.statistics.skill_bonuses["perception"] == 10
    assert creature.statistics.senses == ("Darkvision 120 ft.",)
    assert creature.statistics.passive_perception == 20
    assert creature.statistics.languages == (
        "Deep Speech; telepathy 120 ft.",
    )
    saving_throw = resolve_saving_throw(
        creature,
        "intelligence",
        15,
        roller=lambda _sides: 10,
    )
    assert saving_throw.modifiers.total == 8


def test_bestiary_schema_preserves_unknown_source_fields() -> None:
    [monster] = BestiaryFileSchema.model_validate(
        {
            "monster": [
                {
                    "name": "Test Creature",
                    "source": "TEST",
                    "customFutureField": {"enabled": True},
                }
            ]
        }
    ).monster

    assert monster.model_extra == {"customFutureField": {"enabled": True}}


def test_bestiary_catalog_uses_srd_name_as_public_identity() -> None:
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Protected Name",
            "source": "TEST",
            "srd52": "Public Name",
        }
    )
    catalog = SourceCatalog(
        [monster],
        name_of=lambda record: record.public_name,
        source_of=lambda record: record.source,
    )

    assert catalog.find("Public Name", "test") is monster
    with pytest.raises(KeyError):
        catalog.find("Protected Name", "TEST")


def test_source_catalog_prefers_configured_source_for_unqualified_lookup() -> None:
    classic = BestiaryMonsterSchema(name="Goblin", source="MM")
    revised = BestiaryMonsterSchema(name="Goblin", source="XMM")
    catalog = SourceCatalog(
        [revised, classic],
        name_of=lambda monster: monster.public_name,
        source_of=lambda monster: monster.source,
        source_priority={"MM": 10, "XMM": 20},
    )

    assert catalog.find("Goblin") is revised
    assert catalog.find("Goblin", "MM") is classic


def test_source_catalog_supports_records_without_a_source() -> None:
    record = {"name": "Local Creature"}
    catalog = SourceCatalog(
        [record],
        name_of=lambda value: value["name"],
        source_of=lambda _value: None,
    )

    assert len(catalog) == 1
    assert catalog.find("Local Creature") is record


def test_bestiary_loader_rejects_duplicate_name_and_source(tmp_path: Path) -> None:
    bestiary_dir = tmp_path / "bestiary"
    bestiary_dir.mkdir()
    record = '{"monster": [{"name": "Goblin", "source": "TEST"}]}'
    (bestiary_dir / "bestiary-a.json").write_text(record, encoding="utf-8")
    (bestiary_dir / "bestiary-b.json").write_text(record, encoding="utf-8")

    with pytest.raises(ValueError, match=r"Duplicate content record 'Goblin\\|TEST'"):
        load_bestiary_catalog(tmp_path)
