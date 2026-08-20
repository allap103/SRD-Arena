from srd_arena.content.catalogs import SourceCatalog, load_spell_catalog
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import SpellSchema
from srd_arena.content.translators import build_spell
from srd_arena.domain.spells.rules import spell_max_targets


def test_bundled_spells_load_as_typed_records() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    color_spray = catalog.find("Color Spray", "xphb")

    assert len(catalog) >= 270
    assert isinstance(color_spray, SpellSchema)
    assert color_spray.level == 1
    assert color_spray.school == "I"
    assert color_spray.saving_throw == ["constitution"]
    assert color_spray.condition_inflict == ["blinded"]
    assert color_spray.area_tags == ["N"]


def test_spell_schema_preserves_unknown_source_fields() -> None:
    spell = SpellSchema.model_validate(
        {
            "name": "Test Spell",
            "source": "TEST",
            "level": 1,
            "school": "V",
            "customFutureField": {"enabled": True},
        }
    )

    assert spell.model_extra == {"customFutureField": {"enabled": True}}


def test_spell_translation_builds_combat_ready_domain_spell() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    fireball = build_spell("Fireball", "XPHB", catalog)

    assert fireball.name == "Fireball"
    assert fireball.source == "XPHB"
    assert fireball.level == 3
    assert fireball.saving_throw_abilities == ("dexterity",)
    assert fireball.damage_dice == "8d6"
    assert fireball.damage_inflict == ("fire",)
    assert fireball.geometry_mode == "point_area"
    assert fireball.area_size_feet == 20
    assert fireball.mechanics is not None
    assert fireball.mechanics.resolution == "saving_throw"
    assert fireball.mechanics.damage[0].dice == "8d6"


def test_repeated_attack_and_removal_spells_translate_from_typed_mechanics() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    scorching_ray = build_spell("Scorching Ray", "XPHB", catalog)
    lesser_restoration = build_spell("Lesser Restoration", "XPHB", catalog)

    assert scorching_ray.mechanics is not None
    assert scorching_ray.mechanics.resolution == "spell_attack"
    assert scorching_ray.mechanics.repeat_target_allocations
    assert scorching_ray.mechanics.require_full_target_count
    assert spell_max_targets(scorching_ray, 2) == 3
    assert spell_max_targets(scorching_ray, 3) == 4
    assert lesser_restoration.removable_conditions == (
        "blinded",
        "deafened",
        "paralyzed",
        "poisoned",
    )
    assert lesser_restoration.mechanics is not None
    assert lesser_restoration.mechanics.resolution == "automatic"


def test_wave_1a_spells_define_executable_immediate_mechanics() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    names = {
        "Acid Splash",
        "Blight",
        "Burning Hands",
        "Circle of Death",
        "Cone of Cold",
        "Fire Bolt",
        "Fireball",
        "Flame Strike",
        "Inflict Wounds",
        "Lightning Bolt",
        "Poison Spray",
        "Sacred Flame",
        "Shatter",
    }

    spells = [catalog.find(name, "XPHB") for name in names]

    assert all(spell.executable for spell in spells)
    assert all(
        build_spell(spell.public_name, spell.source, catalog).mechanics
        for spell in spells
    )
    assert catalog.find("Blight", "XPHB").implementation.status == "partial"
    assert catalog.find("Sacred Flame", "XPHB").implementation.status == "complete"


def test_wave_1b_spells_define_executable_condition_mechanics() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    names = {
        "Animal Friendship",
        "Blindness/Deafness",
        "Charm Monster",
        "Charm Person",
        "Color Spray",
        "Greater Invisibility",
        "Hideous Laughter",
        "Hold Monster",
        "Hold Person",
        "Invisibility",
        "Sleep",
    }

    spells = [catalog.find(name, "XPHB") for name in names]

    assert all(spell.executable for spell in spells)
    assert all(
        build_spell(spell.public_name, spell.source, catalog).mechanics
        for spell in spells
    )


def test_spell_catalog_and_translation_use_srd_public_name() -> None:
    source_spell = SpellSchema.model_validate(
        {
            "name": "Protected Hand",
            "source": "TEST",
            "srd52": "Arcane Hand",
            "level": 5,
            "school": "V",
        }
    )
    catalog = SourceCatalog(
        [source_spell],
        name_of=lambda spell: spell.public_name,
        source_of=lambda spell: spell.source,
    )

    spell = build_spell("Arcane Hand", "TEST", catalog)

    assert spell.id == "arcane_hand"
    assert spell.name == "Arcane Hand"
