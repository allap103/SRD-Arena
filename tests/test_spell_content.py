from srd_arena.content.common import SourceCatalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import SpellSchema, build_spell, load_spell_catalog
from srd_arena.domain.spells.rules import (
    spell_duration_rounds,
    spell_max_targets,
)
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
    capability_area_size_feet,
    capability_damage_dice,
    capability_damage_types,
    capability_effects,
    capability_geometry_mode,
    primary_effects,
    capability_removable_conditions,
    capability_removable_effect_kinds,
    capability_remove_effect_selection,
    capability_saving_throw_abilities,
)


def _build_catalog_spell(catalog, name: str, source: str = "XPHB"):
    return build_spell(catalog.find(name, source))


def test_every_bundled_executable_spell_has_a_shared_definition() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    spells = [build_spell(raw) for raw in catalog if raw.capability is not None]

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


def test_spell_builder_creates_combat_ready_domain_spell() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    fireball = _build_catalog_spell(catalog, "Fireball")

    assert fireball.name == "Fireball"
    assert fireball.source == "XPHB"
    assert fireball.level == 3
    assert capability_saving_throw_abilities(fireball.definition) == ("dexterity",)
    assert capability_damage_dice(fireball.definition) == "8d6"
    assert capability_damage_types(fireball.definition) == ("fire",)
    assert capability_geometry_mode(fireball.definition) == "point_area"
    assert capability_area_size_feet(fireball.definition) == 20
    assert fireball.definition is not None
    assert fireball.definition is not None
    assert isinstance(fireball.definition.resolution, SavingThrowResolution)
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "8d6"
        for effect in primary_effects(fireball.definition)
    )


def test_repeated_attack_and_removal_spells_translate_from_typed_capability() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    scorching_ray = _build_catalog_spell(catalog, "Scorching Ray")
    lesser_restoration = _build_catalog_spell(catalog, "Lesser Restoration")

    assert scorching_ray.definition is not None
    assert scorching_ray.definition is not None
    assert isinstance(scorching_ray.definition.resolution, AttackResolution)
    assert scorching_ray.definition is not None
    assert scorching_ray.definition.repetition is not None
    assert scorching_ray.definition.repetition.count == 3
    assert scorching_ray.definition.repetition.allocation == "same_or_different"
    assert spell_max_targets(scorching_ray, 2) == 3
    assert spell_max_targets(scorching_ray, 3) == 4
    assert capability_removable_conditions(lesser_restoration.definition) == (
        "blinded",
        "deafened",
        "paralyzed",
        "poisoned",
    )
    assert lesser_restoration.definition is not None
    assert lesser_restoration.definition is not None
    assert isinstance(lesser_restoration.definition.resolution, AutomaticResolution)


def test_wave_1c_spells_translate_composed_capability() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    ray = _build_catalog_spell(catalog, "Ray of Sickness")
    ice_knife = _build_catalog_spell(catalog, "Ice Knife")
    eldritch_blast = _build_catalog_spell(catalog, "Eldritch Blast")
    weird = _build_catalog_spell(catalog, "Weird")

    assert ray.definition is not None
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
    assert ice_knife.definition is not None
    assert any(
        isinstance(effect, DamageEffect) and effect.damage_type == "piercing"
        for effect in primary_effects(ice_knife.definition)
    )
    follow_up = ice_knife.definition.follow_ups[0]
    assert follow_up.target.size_feet == 5
    assert isinstance(follow_up.resolution, SavingThrowResolution)
    assert any(
        isinstance(effect, DamageEffect) and effect.damage_type == "cold"
        for stage in follow_up.resolution.failure
        for effect in stage.effects
    )
    assert eldritch_blast.definition is not None
    assert spell_max_targets(eldritch_blast, None, caster_level=1) == 1
    assert spell_max_targets(eldritch_blast, None, caster_level=11) == 3
    assert weird.definition is not None
    assert weird.definition is not None
    assert isinstance(weird.definition.resolution, SavingThrowResolution)
    weird_repeat = weird.definition.resolution.failure[0].repeat_saves[0]
    assert weird_repeat.trigger == "end_of_turn"
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "5d10"
        for effect in weird_repeat.failure_effects
    )


def test_healing_spells_translate_restoration_and_slot_scaling() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    cure_wounds = _build_catalog_spell(catalog, "Cure Wounds")
    false_life = _build_catalog_spell(catalog, "False Life")

    assert cure_wounds.definition is not None
    assert cure_wounds.definition is not None
    assert cure_wounds.definition.scaling[0].per_level[0].amount == "2d8"
    assert any(
        isinstance(effect, HealingEffect)
        and effect.dice == "2d8"
        and effect.modifier == "ability_modifier"
        for effect in capability_effects(cure_wounds.definition)
    )
    assert false_life.definition is not None
    assert false_life.definition is not None
    assert false_life.definition.scaling[0].per_level[0].amount == 5
    assert any(
        isinstance(effect, TemporaryHitPointsEffect)
        and effect.dice == "2d4"
        and effect.value == 4
        for effect in capability_effects(false_life.definition)
    )

    healing_word = _build_catalog_spell(catalog, "Healing Word")
    mass_healing_word = _build_catalog_spell(catalog, "Mass Healing Word")
    mass_cure_wounds = _build_catalog_spell(catalog, "Mass Cure Wounds")
    assert healing_word.definition is not None
    assert healing_word.definition is not None
    assert healing_word.definition.scaling[0].per_level[0].amount == "2d4"
    assert mass_healing_word.definition is not None
    assert mass_healing_word.definition is not None
    assert mass_healing_word.definition.target.count.maximum == 6
    assert mass_healing_word.definition.scaling[0].per_level[0].amount == "1d4"
    assert mass_cure_wounds.definition is not None
    assert mass_cure_wounds.definition is not None
    assert mass_cure_wounds.definition.target.occupants == "chosen"
    assert mass_cure_wounds.definition.target.size_feet == 30
    heal = _build_catalog_spell(catalog, "Heal")
    power_word_heal = _build_catalog_spell(catalog, "Power Word Heal")
    assert capability_remove_effect_selection(heal.definition) == "all"
    assert capability_removable_conditions(heal.definition) == (
        "blinded",
        "deafened",
        "poisoned",
    )
    assert heal.definition is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.bonus == 70
        for effect in capability_effects(heal.definition)
    )
    assert heal.definition is not None
    assert heal.definition.scaling[0].per_level[0].amount == 10
    assert capability_remove_effect_selection(power_word_heal.definition) == "all"
    assert power_word_heal.definition is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.restore_to_maximum
        for effect in capability_effects(power_word_heal.definition)
    )
    aid = _build_catalog_spell(catalog, "Aid")
    assert aid.definition is not None
    assert any(
        isinstance(effect, HitPointMaximumModifierEffect)
        and effect.value == 5
        and effect.also_modify_current
        for effect in capability_effects(aid.definition)
    )
    assert aid.definition is not None
    assert aid.definition.scaling[0].per_level[0].amount == 5
    mass_heal = _build_catalog_spell(catalog, "Mass Heal")
    assert mass_heal.definition is not None
    assert any(
        isinstance(effect, HealingEffect) and effect.pool == 700
        for effect in capability_effects(mass_heal.definition)
    )
    assert capability_remove_effect_selection(mass_heal.definition) == "all"


def test_restoration_spells_translate_source_aware_removal() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    greater = _build_catalog_spell(catalog, "Greater Restoration")
    remove_curse = _build_catalog_spell(catalog, "Remove Curse")

    assert capability_removable_conditions(greater.definition) == (
        "charmed",
        "petrified",
    )
    assert capability_removable_effect_kinds(greater.definition) == (
        "condition",
        "curse",
        "hit_point_maximum_reduction",
    )
    assert capability_remove_effect_selection(greater.definition) == "one"
    assert capability_removable_effect_kinds(remove_curse.definition) == ("curse",)
    assert capability_remove_effect_selection(remove_curse.definition) == "all"


def test_protection_from_poison_translates_creature_modifiers() -> None:
    spell = _build_catalog_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT), "Protection from Poison"
    )

    assert capability_removable_conditions(spell.definition) == ("poisoned",)
    assert capability_remove_effect_selection(spell.definition) == "all"
    assert spell.definition is not None
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
    spell = _build_catalog_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT), "Protection from Energy"
    )

    assert spell.definition is not None
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
    bless = _build_catalog_spell(catalog, "Bless")
    bane = _build_catalog_spell(catalog, "Bane")

    assert bless.definition is not None
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
    assert bane.definition is not None
    assert [
        (modifier.roll, modifier.mode, modifier.dice)
        for modifier in primary_effects(bane.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [
        ("attack_roll", "subtract", "1d4"),
        ("saving_throw", "subtract", "1d4"),
    ]


def test_foresight_translates_bidirectional_roll_modes() -> None:
    spell = _build_catalog_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT), "Foresight")

    assert spell.definition is not None
    assert [
        (modifier.roll, modifier.mode, modifier.subject)
        for modifier in primary_effects(spell.definition)
        if isinstance(modifier, RollModifierEffect)
    ] == [
        ("d20_test", "advantage", "target"),
        ("attack_roll", "disadvantage", "attacks_against_target"),
    ]
    assert spell.definition.reactivation_ends_previous
    assert spell_duration_rounds(spell) == 4800


def test_shield_of_faith_translates_sourced_armor_class() -> None:
    spell = _build_catalog_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT), "Shield of Faith"
    )

    assert spell.definition is not None
    assert any(
        isinstance(effect, ArmorClassModifierEffect) and effect.value == 2
        for effect in capability_effects(spell.definition)
    )
    assert spell.concentration
    assert spell_duration_rounds(spell) == 100


def test_sense_spells_and_blur_translate_directional_perception() -> None:
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    darkvision = _build_catalog_spell(catalog, "Darkvision")
    true_seeing = _build_catalog_spell(catalog, "True Seeing")
    blur = _build_catalog_spell(catalog, "Blur")

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
    assert blur.definition is not None
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
    longstrider = _build_catalog_spell(catalog, "Longstrider")
    ray_of_frost = _build_catalog_spell(catalog, "Ray of Frost")

    assert longstrider.definition is not None
    assert any(
        isinstance(effect, SpeedModifierEffect) and effect.feet == 10
        for effect in capability_effects(longstrider.definition)
    )
    assert spell_duration_rounds(longstrider) == 600
    assert longstrider.definition is not None
    assert longstrider.definition.scaling[0].per_level[0].kind == "target_count"
    assert ray_of_frost.definition is not None
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
    spell = _build_catalog_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT), "Resistance")

    assert spell.definition is not None
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
    spell = _build_catalog_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT), "Heroism")

    assert spell.definition is not None
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
    spell = _build_catalog_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT), "Stoneskin")

    assert spell.definition is not None
    assert any(
        isinstance(effect, DamageResistanceEffect)
        and effect.damage_types == ("bludgeoning", "piercing", "slashing")
        and effect.selection == "all"
        for effect in capability_effects(spell.definition)
    )
    assert spell.concentration
    assert spell_duration_rounds(spell) == 600


def test_enhance_ability_translates_ability_scoped_choices() -> None:
    spell = _build_catalog_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT), "Enhance Ability"
    )

    assert spell.definition is not None
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
    spell = _build_catalog_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT), "Faerie Fire")

    assert capability_geometry_mode(spell.definition) == "point_area"
    assert spell.definition is not None
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
    spell = _build_catalog_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT), "Phantasmal Killer"
    )

    assert spell.definition is not None
    assert spell.definition is not None
    assert isinstance(spell.definition.resolution, SavingThrowResolution)
    assert spell.definition.resolution.success_damage == "half"
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "4d10"
        for effect in primary_effects(spell.definition)
    )
    repeat = spell.definition.resolution.failure[0].repeat_saves[0]
    assert repeat.trigger == "end_of_turn"
    assert any(
        isinstance(effect, DamageEffect) and effect.dice == "4d10"
        for effect in repeat.failure_effects
    )
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
    assert all(build_spell(spell).definition for spell in spells)
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
    assert all(build_spell(spell).definition for spell in spells)


def test_spell_catalog_and_builder_use_srd_public_name() -> None:
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

    spell = build_spell(catalog.find("Arcane Hand", "TEST"))

    assert spell.id == "arcane_hand"
    assert spell.name == "Arcane Hand"
