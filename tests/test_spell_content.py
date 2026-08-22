from srd_arena.content.common import SourceCatalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import SpellSchema, build_spell, load_spell_catalog
from srd_arena.domain.spells.rules import spell_duration_rounds, spell_max_targets
from srd_arena.domain.capabilities import (
    AttackResolution,
    ArmorClassModifierEffect,
    AutomaticResolution,
    ConditionEffect,
    ConditionImmunityEffect,
    ConditionSaveAdvantageEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    DamageEffect,
    HealingEffect,
    HitPointMaximumModifierEffect,
    RollModifierEffect,
    SenseEffect,
    SavingThrowResolution,
    SpeedModifierEffect,
    TemporaryHitPointsEffect,
    capability_effects,
    primary_effects,
)


def test_every_bundled_executable_spell_has_a_shared_definition() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    spells = [
        build_spell(raw.public_name, raw.source, catalog)
        for raw in catalog
        if raw.capability is not None
    ]

    assert len(spells) >= 50
    assert [spell.name for spell in spells if spell.definition is None] == []


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
    assert fireball.capability is not None
    assert fireball.definition is not None
    assert isinstance(fireball.definition.resolution, SavingThrowResolution)
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "8d6"
        for effect in primary_effects(fireball.definition)
    )


def test_repeated_attack_and_removal_spells_translate_from_typed_capability() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    scorching_ray = build_spell("Scorching Ray", "XPHB", catalog)
    lesser_restoration = build_spell("Lesser Restoration", "XPHB", catalog)

    assert scorching_ray.capability is not None
    assert scorching_ray.definition is not None
    assert isinstance(scorching_ray.definition.resolution, AttackResolution)
    assert scorching_ray.definition is not None
    assert scorching_ray.definition.repetition is not None
    assert scorching_ray.definition.repetition.count == 3
    assert scorching_ray.definition.repetition.allocation == "same_or_different"
    assert spell_max_targets(scorching_ray, 2) == 3
    assert spell_max_targets(scorching_ray, 3) == 4
    assert lesser_restoration.removable_conditions == (
        "blinded",
        "deafened",
        "paralyzed",
        "poisoned",
    )
    assert lesser_restoration.capability is not None
    assert lesser_restoration.definition is not None
    assert isinstance(lesser_restoration.definition.resolution, AutomaticResolution)


def test_wave_1c_spells_translate_composed_capability() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    ray = build_spell("Ray of Sickness", "XPHB", catalog)
    ice_knife = build_spell("Ice Knife", "XPHB", catalog)
    eldritch_blast = build_spell("Eldritch Blast", "XPHB", catalog)
    weird = build_spell("Weird", "XPHB", catalog)

    assert ray.capability is not None
    assert any(
        isinstance(effect, ConditionEffect) and effect.condition == "poisoned"
        for effect in primary_effects(ray.definition)
    )
    assert any(
        isinstance(effect, ConditionEffect)
        and effect.duration is not None
        and effect.duration.kind == "end_of_turn"
        and effect.duration.creature == "source"
        for effect in primary_effects(ray.definition)
    )
    assert ice_knife.capability is not None
    assert any(
        isinstance(effect, DamageEffect) and effect.damage_type == "piercing"
        for effect in primary_effects(ice_knife.definition)
    )
    assert ice_knife.capability.follow_up_resolutions[0].area_radius_feet == 5
    assert ice_knife.capability.follow_up_resolutions[0].damage[0].damage_type == "cold"
    assert eldritch_blast.capability is not None
    assert spell_max_targets(eldritch_blast, None, caster_level=1) == 1
    assert spell_max_targets(eldritch_blast, None, caster_level=11) == 3
    assert weird.capability is not None
    assert weird.capability.repeat_save_trigger == "end_of_turn"
    assert weird.capability.repeat_failure_damage[0].dice == "5d10"


def test_healing_spells_translate_restoration_and_slot_scaling() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    cure_wounds = build_spell("Cure Wounds", "XPHB", catalog)
    false_life = build_spell("False Life", "XPHB", catalog)

    assert cure_wounds.capability is not None
    assert cure_wounds.definition is not None
    assert cure_wounds.definition.scaling[0].per_level[0].amount == "2d8"
    assert any(
        isinstance(effect, HealingEffect)
        and effect.dice == "2d8"
        and effect.modifier == "ability_modifier"
        for effect in capability_effects(cure_wounds.definition)
    )
    assert false_life.capability is not None
    assert false_life.definition is not None
    assert false_life.definition.scaling[0].per_level[0].amount == 5
    assert any(
        isinstance(effect, TemporaryHitPointsEffect)
        and effect.dice == "2d4"
        and effect.value == 4
        for effect in capability_effects(false_life.definition)
    )

    healing_word = build_spell("Healing Word", "XPHB", catalog)
    mass_healing_word = build_spell("Mass Healing Word", "XPHB", catalog)
    mass_cure_wounds = build_spell("Mass Cure Wounds", "XPHB", catalog)
    assert healing_word.capability is not None
    assert healing_word.definition is not None
    assert healing_word.definition.scaling[0].per_level[0].amount == "2d4"
    assert mass_healing_word.capability is not None
    assert mass_healing_word.definition is not None
    assert mass_healing_word.definition.target.count.maximum == 6
    assert mass_healing_word.definition.scaling[0].per_level[0].amount == "1d4"
    assert mass_cure_wounds.capability is not None
    assert mass_cure_wounds.definition is not None
    assert mass_cure_wounds.definition.target.occupants == "chosen"
    assert mass_cure_wounds.definition.target.size_feet == 30
    heal = build_spell("Heal", "XPHB", catalog)
    power_word_heal = build_spell("Power Word Heal", "XPHB", catalog)
    assert heal.remove_effect_selection == "all"
    assert heal.removable_conditions == ("blinded", "deafened", "poisoned")
    assert heal.capability is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.bonus == 70
        for effect in capability_effects(heal.definition)
    )
    assert heal.definition is not None
    assert heal.definition.scaling[0].per_level[0].amount == 10
    assert power_word_heal.remove_effect_selection == "all"
    assert power_word_heal.capability is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.restore_to_maximum
        for effect in capability_effects(power_word_heal.definition)
    )
    aid = build_spell("Aid", "XPHB", catalog)
    assert aid.capability is not None
    assert any(
        isinstance(effect, HitPointMaximumModifierEffect)
        and effect.value == 5
        and effect.also_modify_current
        for effect in capability_effects(aid.definition)
    )
    assert aid.definition is not None
    assert aid.definition.scaling[0].per_level[0].amount == 5
    mass_heal = build_spell("Mass Heal", "XPHB", catalog)
    assert mass_heal.capability is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.pool == 700
        for effect in capability_effects(mass_heal.definition)
    )
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
    assert spell.capability is not None
    effects = capability_effects(spell.definition)
    assert any(
        isinstance(effect, DamageResistanceEffect)
        and effect.damage_types == ("poison",)
        for effect in effects
    )
    assert any(
        isinstance(effect, ConditionSaveAdvantageEffect)
        and effect.conditions == ("poisoned",)
        for effect in effects
    )
    assert spell_duration_rounds(spell) == 600


def test_protection_from_energy_translates_a_resistance_choice() -> None:
    spell = build_spell(
        "Protection from Energy", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.capability is not None
    assert any(
        isinstance(effect, DamageResistanceEffect)
        and effect.selection == "choose_one"
        and effect.damage_types == ("acid", "cold", "fire", "lightning", "thunder")
        for effect in capability_effects(spell.definition)
    )
    assert spell.concentration
    assert spell_duration_rounds(spell) == 600


def test_bless_and_bane_translate_sourced_roll_modifiers() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    bless = build_spell("Bless", "XPHB", catalog)
    bane = build_spell("Bane", "XPHB", catalog)

    assert bless.capability is not None
    assert [
        (modifier.roll, modifier.mode, modifier.dice)
        for modifier in primary_effects(bless.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [
        ("attack_roll", "add", "1d4"),
        ("saving_throw", "add", "1d4"),
    ]
    assert bless.definition is not None
    assert bless.definition.target.count.maximum == 3
    assert bless.definition is not None
    assert bless.definition.scaling[0].per_level[0].kind == "target_count"
    assert bless.definition.scaling[0].per_level[0].amount == 1
    assert bane.capability is not None
    assert [
        (modifier.roll, modifier.mode, modifier.dice)
        for modifier in primary_effects(bane.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [
        ("attack_roll", "subtract", "1d4"),
        ("saving_throw", "subtract", "1d4"),
    ]


def test_foresight_translates_bidirectional_roll_modes() -> None:
    spell = build_spell("Foresight", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.capability is not None
    assert [
        (modifier.roll, modifier.mode, modifier.subject)
        for modifier in primary_effects(spell.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [
        ("d20_test", "advantage", "target"),
        ("attack_roll", "disadvantage", "attacks_against_target"),
    ]
    assert spell.recast_ends_previous
    assert spell_duration_rounds(spell) == 4800


def test_shield_of_faith_translates_sourced_armor_class() -> None:
    spell = build_spell(
        "Shield of Faith", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.capability is not None
    assert any(
        isinstance(effect, ArmorClassModifierEffect) and effect.value == 2
        for effect in capability_effects(spell.definition)
    )
    assert spell.concentration
    assert spell_duration_rounds(spell) == 100


def test_sense_spells_and_blur_translate_directional_perception() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    darkvision = build_spell("Darkvision", "XPHB", catalog)
    true_seeing = build_spell("True Seeing", "XPHB", catalog)
    blur = build_spell("Blur", "XPHB", catalog)

    assert any(
        isinstance(effect, SenseEffect)
        and (effect.sense, effect.range_feet) == ("darkvision", 150)
        for effect in capability_effects(darkvision.definition)
    )
    assert any(
        isinstance(effect, SenseEffect)
        and (effect.sense, effect.range_feet) == ("truesight", 120)
        for effect in capability_effects(true_seeing.definition)
    )
    assert blur.capability is not None
    defensive = next(
        effect
        for effect in primary_effects(blur.definition)
        if isinstance(effect, RollModifierEffect)
    )
    assert defensive.subject == "attacks_against_target"
    assert defensive.mode == "disadvantage"
    assert defensive.ignored_by_senses == ("blindsight", "truesight")


def test_speed_spells_translate_additive_modifiers() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    longstrider = build_spell("Longstrider", "XPHB", catalog)
    ray_of_frost = build_spell("Ray of Frost", "XPHB", catalog)

    assert longstrider.capability is not None
    assert any(
        isinstance(effect, SpeedModifierEffect) and effect.feet == 10
        for effect in capability_effects(longstrider.definition)
    )
    assert spell_duration_rounds(longstrider) == 600
    assert longstrider.definition is not None
    assert longstrider.definition.scaling[0].per_level[0].kind == "target_count"
    assert ray_of_frost.capability is not None
    assert any(
        isinstance(effect, SpeedModifierEffect)
        and effect.feet == -10
        and effect.duration is not None
        and effect.duration.kind == "start_of_turn"
        for effect in capability_effects(ray_of_frost.definition)
    )
    assert ray_of_frost.definition is not None
    assert tuple(
        (threshold.minimum_level, threshold.increments[0].amount)
        for scaling in ray_of_frost.definition.scaling
        if scaling.basis == "actor_level"
        for threshold in scaling.thresholds
    ) == ((1, "1d8"), (5, "2d8"), (11, "3d8"), (17, "4d8"))


def test_resistance_translates_typed_per_turn_damage_reduction() -> None:
    spell = build_spell("Resistance", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.capability is not None
    reduction = next(
        effect
        for effect in capability_effects(spell.definition)
        if isinstance(effect, DamageReductionEffect)
    )
    assert reduction.selection == "choose_one"
    assert reduction.dice == "1d4"
    assert "fire" in reduction.damage_types
    assert "force" not in reduction.damage_types
    assert spell.concentration
    assert spell_duration_rounds(spell) == 10


def test_heroism_translates_immunity_and_turn_start_temporary_hp() -> None:
    spell = build_spell("Heroism", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.capability is not None
    effects = capability_effects(spell.definition)
    assert any(
        isinstance(effect, ConditionImmunityEffect)
        and effect.conditions == ("frightened",)
        for effect in effects
    )
    assert any(
        isinstance(effect, TemporaryHitPointsEffect)
        and effect.trigger == "target_turn_start"
        and effect.modifier == "ability_modifier"
        for effect in effects
    )
    assert spell.definition is not None
    assert spell.definition.scaling[0].per_level[0].kind == "target_count"


def test_stoneskin_translates_multiple_damage_resistances() -> None:
    spell = build_spell("Stoneskin", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.capability is not None
    assert any(
        isinstance(effect, DamageResistanceEffect)
        and effect.damage_types == ("bludgeoning", "piercing", "slashing")
        and effect.selection == "all"
        for effect in capability_effects(spell.definition)
    )
    assert spell.concentration
    assert spell_duration_rounds(spell) == 600


def test_enhance_ability_translates_ability_scoped_choices() -> None:
    spell = build_spell(
        "Enhance Ability", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.capability is not None
    modifier = next(
        effect
        for effect in primary_effects(spell.definition)
        if isinstance(effect, RollModifierEffect)
    )
    assert modifier.ability_options == (
        "strength",
        "dexterity",
        "intelligence",
        "wisdom",
        "charisma",
    )


def test_faerie_fire_translates_cube_and_incoming_attack_advantage() -> None:
    spell = build_spell("Faerie Fire", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))

    assert spell.geometry_mode == "point_area"
    assert spell.capability is not None
    assert spell.definition is not None
    assert spell.definition.target.shape == "cube"
    assert spell.definition.target.size_feet == 20
    assert isinstance(spell.definition.resolution, SavingThrowResolution)
    assert spell.definition.resolution.ability == "dexterity"
    assert [
        (modifier.roll, modifier.mode, modifier.subject)
        for modifier in primary_effects(spell.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [("attack_roll", "advantage", "attacks_against_target")]


def test_phantasmal_killer_translates_repeat_damage_and_roll_disadvantage() -> None:
    spell = build_spell(
        "Phantasmal Killer", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert spell.capability is not None
    assert spell.definition is not None
    assert isinstance(spell.definition.resolution, SavingThrowResolution)
    assert spell.definition.resolution.success_damage == "half"
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "4d10"
        for effect in primary_effects(spell.definition)
    )
    assert spell.capability.repeat_save_trigger == "end_of_turn"
    assert spell.capability.repeat_failure_damage[0].dice == "4d10"
    assert spell.definition.scaling[0].per_level[0].amount == "1d10"
    assert {
        (modifier.roll, modifier.mode)
        for modifier in primary_effects(spell.definition)
        if isinstance(modifier, RollModifierEffect)
    } == {
        ("ability_check", "disadvantage"),
        ("attack_roll", "disadvantage"),
    }


def test_wave_1a_spells_define_executable_translate_capability() -> None:
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
        build_spell(spell.public_name, spell.source, catalog).capability
        for spell in spells
    )
    assert catalog.find("Blight", "XPHB").implementation.status == "partial"
    assert catalog.find("Sacred Flame", "XPHB").implementation.status == "complete"


def test_wave_1b_spells_define_executable_condition_capability() -> None:
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
        build_spell(spell.public_name, spell.source, catalog).capability
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
