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


def test_wave_1c_spells_translate_composed_mechanics() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    ray = build_spell("Ray of Sickness", "XPHB", catalog)
    ice_knife = build_spell("Ice Knife", "XPHB", catalog)
    eldritch_blast = build_spell("Eldritch Blast", "XPHB", catalog)
    weird = build_spell("Weird", "XPHB", catalog)

    assert ray.mechanics is not None
    assert ray.mechanics.conditions == ("poisoned",)
    assert ray.mechanics.expires_on_source_turn_end
    assert ice_knife.mechanics is not None
    assert ice_knife.mechanics.damage[0].damage_type == "piercing"
    assert ice_knife.mechanics.follow_up_resolutions[0].area_radius_feet == 5
    assert ice_knife.mechanics.follow_up_resolutions[0].damage[0].damage_type == "cold"
    assert eldritch_blast.mechanics is not None
    assert spell_max_targets(eldritch_blast, None, caster_level=1) == 1
    assert spell_max_targets(eldritch_blast, None, caster_level=11) == 3
    assert weird.mechanics is not None
    assert weird.mechanics.repeat_save_trigger == "end_of_turn"
    assert weird.mechanics.repeat_failure_damage[0].dice == "5d10"


def test_healing_spells_translate_restoration_and_slot_scaling() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    cure_wounds = build_spell("Cure Wounds", "XPHB", catalog)
    false_life = build_spell("False Life", "XPHB", catalog)

    assert cure_wounds.mechanics is not None
    assert cure_wounds.mechanics.healing[0].dice == "2d8"
    assert cure_wounds.mechanics.healing[0].add_spellcasting_modifier
    assert cure_wounds.mechanics.slot_healing_dice_increment == "2d8"
    assert false_life.mechanics is not None
    assert false_life.mechanics.temporary_hit_points[0].dice == "2d4"
    assert false_life.mechanics.temporary_hit_points[0].value == 4
    assert false_life.mechanics.slot_temporary_hit_points_increment == 5


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
