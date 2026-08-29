from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import SpellSchema, build_spell, load_spell_catalog
from srd_arena.domain.spells import (
    SpellCastingTime,
    SpellComponents,
    SpellDuration,
    SpellMaterialComponent,
    SpellRange,
    SpellRangeDistance,
)


def test_spell_builder_translates_intrinsic_metadata_to_domain_values() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    fireball = build_spell(catalog.find("Fireball", "XPHB"))

    assert fireball.casting_times == (SpellCastingTime(1, "action"),)
    assert fireball.range == SpellRange(
        "point",
        SpellRangeDistance("feet", 150),
    )
    assert fireball.durations == (SpellDuration("instant"),)
    assert fireball.components == SpellComponents(
        verbal=True,
        somatic=True,
        material=SpellMaterialComponent("a ball of bat guano and sulfur"),
    )


def test_spell_builder_preserves_alternative_casting_times_and_material_rules() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    plant_growth = build_spell(catalog.find("Plant Growth", "XPHB"))
    restoration = build_spell(catalog.find("Greater Restoration", "XPHB"))

    assert plant_growth.casting_times == (
        SpellCastingTime(1, "action", label="Overgrowth"),
        SpellCastingTime(8, "hour", label="Enrichment"),
    )
    assert restoration.components.material == SpellMaterialComponent(
        "diamond dust worth 100+ GP, which the spell consumes",
        cost_copper=10_000,
        consumed=True,
    )


def test_domain_spell_metadata_is_immutable() -> None:
    distance = SpellRangeDistance("feet", 60)
    amount_attribute = "amount"

    with pytest.raises(FrozenInstanceError):
        setattr(distance, amount_attribute, 30)


@pytest.mark.parametrize(
    "field,value,message",
    [
        (
            "range",
            {"type": "point", "distance": {"type": "feet"}},
            "Numeric spell distances require an amount",
        ),
        (
            "duration",
            [{"type": "timed"}],
            "Timed spell durations require duration details",
        ),
    ],
)
def test_spell_schema_rejects_incomplete_executable_metadata(
    field: str,
    value: object,
    message: str,
) -> None:
    source: dict[str, object] = {
        "name": "Invalid Spell",
        "source": "TEST",
        "level": 1,
        "school": "V",
        field: value,
    }

    with pytest.raises(ValidationError, match=message):
        SpellSchema.model_validate(source)
