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

    healing_word = build_spell("Healing Word", "XPHB", catalog)
    mass_healing_word = build_spell("Mass Healing Word", "XPHB", catalog)
    mass_cure_wounds = build_spell("Mass Cure Wounds", "XPHB", catalog)
    assert healing_word.mechanics is not None
    assert healing_word.mechanics.slot_healing_dice_increment == "2d4"
    assert mass_healing_word.mechanics is not None
    assert mass_healing_word.mechanics.base_target_count == 6
    assert mass_healing_word.mechanics.slot_healing_dice_increment == "1d4"
    assert mass_cure_wounds.mechanics is not None
    assert mass_cure_wounds.mechanics.choose_area_targets
    assert mass_cure_wounds.mechanics.area_radius_feet == 30
    heal = build_spell("Heal", "XPHB", catalog)
    power_word_heal = build_spell("Power Word Heal", "XPHB", catalog)
    assert heal.remove_effect_selection == "all"
    assert heal.removable_conditions == ("blinded", "deafened", "poisoned")
    assert heal.mechanics is not None
    assert heal.mechanics.healing[0].bonus == 70
    assert heal.mechanics.slot_healing_bonus_increment == 10
    assert power_word_heal.remove_effect_selection == "all"
    assert power_word_heal.mechanics is not None
    assert power_word_heal.mechanics.healing[0].restore_to_maximum
    aid = build_spell("Aid", "XPHB", catalog)
    assert aid.mechanics is not None
    assert aid.mechanics.maximum_hit_point_modifier == 5
    assert aid.mechanics.also_modify_current_hit_points
    assert aid.mechanics.slot_maximum_hit_point_increment == 5
    mass_heal = build_spell("Mass Heal", "XPHB", catalog)
    assert mass_heal.mechanics is not None
    assert mass_heal.mechanics.healing_pool == 700
    assert mass_heal.remove_effect_selection == "all"


def test_restoration_spells_translate_source_aware_removal() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    greater = build_spell("Greater Restoration", "XPHB", catalog)
    remove_curse = build_spell("Remove Curse", "XPHB", catalog)

    assert greater.removable_conditions == ("charmed", "petrified")
    assert greater.removable_effect_kinds == (
        "condition",
        "curse",
        "hit_point_maximum_reduction",
    )
    assert greater.remove_effect_selection == "one"
    assert remove_curse.removable_effect_kinds == ("curse",)
    assert remove_curse.remove_effect_selection == "all"


def test_protection_from_poison_translates_creature_modifiers() -> None:
    spell = build_spell(
        "Protection from Poison", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.removable_conditions == ("poisoned",)
    assert spell.remove_effect_selection == "all"
    assert spell.mechanics is not None
    assert spell.mechanics.damage_resistances == ("poison",)
    assert spell.mechanics.condition_save_advantages == ("poisoned",)
    assert spell.mechanics.duration_rounds == 600


def test_protection_from_energy_translates_a_resistance_choice() -> None:
    spell = build_spell(
        "Protection from Energy", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.mechanics is not None
    assert spell.mechanics.damage_resistances == (
        "acid",
        "cold",
        "fire",
        "lightning",
        "thunder",
    )
    assert spell.mechanics.damage_resistance_choice
    assert spell.mechanics.concentration
    assert spell.mechanics.duration_rounds == 600


def test_bless_and_bane_translate_sourced_roll_modifiers() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    bless = build_spell("Bless", "XPHB", catalog)
    bane = build_spell("Bane", "XPHB", catalog)

    assert bless.mechanics is not None
    assert [
        (modifier.roll, modifier.mode, modifier.dice)
        for modifier in bless.mechanics.roll_modifiers
    ] == [
        ("attack_roll", "add", "1d4"),
        ("saving_throw", "add", "1d4"),
    ]
    assert bless.mechanics.base_target_count == 3
    assert bless.mechanics.slot_target_increment == 1
    assert bane.mechanics is not None
    assert [
        (modifier.roll, modifier.mode, modifier.dice)
        for modifier in bane.mechanics.roll_modifiers
    ] == [
        ("attack_roll", "subtract", "1d4"),
        ("saving_throw", "subtract", "1d4"),
    ]


def test_foresight_translates_bidirectional_roll_modes() -> None:
    spell = build_spell("Foresight", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.mechanics is not None
    assert [
        (modifier.roll, modifier.mode, modifier.subject)
        for modifier in spell.mechanics.roll_modifiers
    ] == [
        ("ability_check", "advantage", "target"),
        ("attack_roll", "advantage", "target"),
        ("saving_throw", "advantage", "target"),
        ("attack_roll", "disadvantage", "attacks_against_target"),
    ]
    assert spell.mechanics.recast_ends_previous
    assert spell.mechanics.duration_rounds == 4800


def test_shield_of_faith_translates_sourced_armor_class() -> None:
    spell = build_spell(
        "Shield of Faith", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.mechanics is not None
    assert spell.mechanics.armor_class_modifier == 2
    assert spell.mechanics.concentration
    assert spell.mechanics.duration_rounds == 100


def test_sense_spells_and_blur_translate_directional_perception() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    darkvision = build_spell("Darkvision", "XPHB", catalog)
    true_seeing = build_spell("True Seeing", "XPHB", catalog)
    blur = build_spell("Blur", "XPHB", catalog)

    assert darkvision.mechanics is not None
    assert darkvision.mechanics.senses == (("darkvision", 150),)
    assert true_seeing.mechanics is not None
    assert true_seeing.mechanics.senses == (("truesight", 120),)
    assert blur.mechanics is not None
    defensive = blur.mechanics.roll_modifiers[0]
    assert defensive.subject == "attacks_against_target"
    assert defensive.mode == "disadvantage"
    assert defensive.ignored_by_senses == ("blindsight", "truesight")


def test_speed_spells_translate_additive_modifiers() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    longstrider = build_spell("Longstrider", "XPHB", catalog)
    ray_of_frost = build_spell("Ray of Frost", "XPHB", catalog)

    assert longstrider.mechanics is not None
    assert longstrider.mechanics.speed_modifier_feet == 10
    assert longstrider.mechanics.duration_rounds == 600
    assert longstrider.mechanics.slot_target_increment == 1
    assert ray_of_frost.mechanics is not None
    assert ray_of_frost.mechanics.speed_modifier_feet == -10
    assert ray_of_frost.mechanics.speed_modifier_duration_rounds == 1
    assert ray_of_frost.mechanics.cantrip_damage_by_level == (
        (1, "1d8"),
        (5, "2d8"),
        (11, "3d8"),
        (17, "4d8"),
    )


def test_resistance_translates_typed_per_turn_damage_reduction() -> None:
    spell = build_spell("Resistance", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.mechanics is not None
    assert spell.mechanics.damage_reduction_choice
    assert spell.mechanics.damage_reduction_dice == "1d4"
    assert "fire" in spell.mechanics.damage_reduction_types
    assert "force" not in spell.mechanics.damage_reduction_types
    assert spell.mechanics.concentration
    assert spell.mechanics.duration_rounds == 10


def test_heroism_translates_immunity_and_turn_start_temporary_hp() -> None:
    spell = build_spell("Heroism", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.mechanics is not None
    assert spell.mechanics.condition_immunities == ("frightened",)
    assert spell.mechanics.temporary_hit_points[0].trigger == "target_turn_start"
    assert spell.mechanics.temporary_hit_points[0].add_spellcasting_modifier
    assert spell.mechanics.slot_target_increment == 1


def test_stoneskin_translates_multiple_damage_resistances() -> None:
    spell = build_spell("Stoneskin", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.mechanics is not None
    assert spell.mechanics.damage_resistances == (
        "bludgeoning",
        "piercing",
        "slashing",
    )
    assert not spell.mechanics.damage_resistance_choice
    assert spell.mechanics.concentration
    assert spell.mechanics.duration_rounds == 600


def test_enhance_ability_translates_ability_scoped_choices() -> None:
    spell = build_spell(
        "Enhance Ability", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.mechanics is not None
    assert spell.mechanics.roll_modifier_ability_choices == (
        "strength",
        "dexterity",
        "intelligence",
        "wisdom",
        "charisma",
    )
    assert [modifier.ability for modifier in spell.mechanics.roll_modifiers] == [
        "strength",
        "dexterity",
        "intelligence",
        "wisdom",
        "charisma",
    ]


def test_faerie_fire_translates_cube_and_incoming_attack_advantage() -> None:
    spell = build_spell("Faerie Fire", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.geometry_mode == "point_area"
    assert spell.mechanics is not None
    assert spell.mechanics.area_shape == "cube"
    assert spell.mechanics.area_length_feet == 20
    assert spell.mechanics.save_ability == "dexterity"
    assert [
        (modifier.roll, modifier.mode, modifier.subject)
        for modifier in spell.mechanics.roll_modifiers
    ] == [("attack_roll", "advantage", "attacks_against_target")]


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
