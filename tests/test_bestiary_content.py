import re
from pathlib import Path

import pytest

from srd_arena.content.catalogs import SourceCatalog, load_bestiary_catalog
from srd_arena.content.loaders.creatures import build_creature
from srd_arena.content.loaders.stat_block_actions import (
    build_stat_block_actions,
)
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import (
    AttackActionMechanicsSchema,
    BestiaryFileSchema,
    BestiaryMonsterSchema,
    CreatureSchema,
    SavingThrowActionMechanicsSchema,
)
from srd_arena.content.schemas.multiattack import (
    ChoiceStepSchema,
    StatBlockActionInvocationSchema,
)
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw
from srd_arena.domain.creatures import (
    AutomaticActionDefinition,
    AttackActionDefinition,
    AttackRollModeRequirement,
    ActionResource,
    DamageEffect,
    SavingThrowActionDefinition,
    SpellcastingActionDefinition,
)
from srd_arena.domain.encounters.actions.attack_resolution import resolve_attack
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.conditions import build_applied_condition
from srd_arena.domain.effects.condition_rules import effective_conditions


def test_bundled_bestiary_loads_as_typed_records() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    goblin = catalog.find("Goblin Warrior", "xmm")
    aboleth = catalog.find("Aboleth", "xmm")

    assert len(catalog) >= 300
    assert isinstance(goblin, BestiaryMonsterSchema)
    assert goblin.armor_class == 15
    assert goblin.average_hit_points == 10
    assert goblin.walk_speed == 30
    assert goblin.speed.walk == 30
    assert [action.name for action in goblin.action] == ["Scimitar", "Shortbow"]
    scimitar = goblin.action[0].mechanics
    shortbow = goblin.action[1].mechanics
    assert isinstance(scimitar, AttackActionMechanicsSchema)
    assert scimitar.attack_modes == ["melee"]
    assert scimitar.attack_bonus == 4
    assert scimitar.target.range_feet == 5
    assert scimitar.reach_feet == 5
    assert scimitar.hit[0].dice == "1d6"
    assert scimitar.hit[0].bonus == 2
    assert scimitar.hit[0].damage_type == "slashing"
    assert scimitar.hit[1].dice == "1d4"
    assert scimitar.hit[1].requirements[0].mode == "advantage"
    assert isinstance(shortbow, AttackActionMechanicsSchema)
    assert shortbow.attack_modes == ["ranged"]
    assert shortbow.attack_bonus == 4
    assert shortbow.target.range_feet == 80
    assert shortbow.range_normal_feet == 80
    assert shortbow.range_long_feet == 320
    assert shortbow.hit[0].dice == "1d6"
    assert shortbow.hit[0].bonus == 2
    assert shortbow.hit[0].damage_type == "piercing"
    assert shortbow.hit[1].dice == "1d4"
    assert shortbow.hit[1].requirements[0].mode == "advantage"
    multiattack = aboleth.action[0].mechanics
    assert multiattack is not None
    assert multiattack.plans[0].steps[0].times == 2
    assert [
        option.name
        for option in multiattack.plans[0].steps[1].options
    ] == ["Consume Memories", "Dominate Mind (2/Day)"]

    air_elemental = catalog.find("Air Elemental", "XMM")
    assert air_elemental.speed.walk == 10
    assert air_elemental.speed.fly is not None
    assert air_elemental.speed.feet_for("fly") == 90
    assert air_elemental.speed.can_hover is True


def test_goblin_actions_build_from_typed_bestiary_mechanics() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    creature = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "goblin",
                "stat_block": {"name": "Goblin Warrior", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )

    scimitar = creature.stat_block_actions["Scimitar"]
    shortbow = creature.stat_block_actions["Shortbow"]
    assert isinstance(scimitar, AttackActionDefinition)
    assert scimitar.attack_modes == ("melee",)
    assert scimitar.hit == (
        DamageEffect("1d6", 2, "slashing"),
        DamageEffect(
            "1d4",
            0,
            "slashing",
            requirements=(AttackRollModeRequirement("advantage"),),
        ),
    )
    assert isinstance(shortbow, AttackActionDefinition)
    assert shortbow.attack_modes == ("ranged",)
    assert shortbow.range_normal_feet == 80
    assert shortbow.range_long_feet == 320
    assert shortbow.hit == (
        DamageEffect("1d6", 2, "piercing"),
        DamageEffect(
            "1d4",
            0,
            "piercing",
            requirements=(AttackRollModeRequirement("advantage"),),
        ),
    )


def test_black_pudding_loads_condition_immunities() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    pudding = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "black_pudding",
                "stat_block": {"name": "Black Pudding", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )

    assert Condition.PRONE in pudding.statistics.condition_immunities
    assert Condition.UNCONSCIOUS not in pudding.statistics.condition_immunities
    unconscious = build_applied_condition(
        condition=Condition.UNCONSCIOUS,
        source_ref="spellcaster",
        source_label="Spellcaster",
        target_ref=pudding.id,
    )

    effective = effective_conditions(
        (unconscious,),
        pudding.statistics.condition_immunities,
    )

    assert effective.has(Condition.UNCONSCIOUS)
    assert effective.has(Condition.INCAPACITATED)
    assert effective.has(Condition.PRONE) is False


def test_goblin_conditional_damage_requires_resolved_advantage() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    goblin = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "goblin",
                "stat_block": {"name": "Goblin Warrior", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )

    advantage_rolls = iter([18, 10])
    with_advantage = resolve_attack(
        goblin,
        goblin,
        attacker_label="Goblin",
        target_label="Goblin",
        preferred_attack_name="Scimitar",
        attack_roll_mode_override="advantage",
        d20_roller=lambda _sides: next(advantage_rolls),
        dice_roller=lambda _count, sides: sides,
    )
    without_advantage = resolve_attack(
        goblin,
        goblin,
        attacker_label="Goblin",
        target_label="Goblin",
        preferred_attack_name="Scimitar",
        attack_roll_mode_override="normal",
        d20_roller=lambda _sides: 18,
        dice_roller=lambda _count, sides: sides,
    )

    assert with_advantage.damage == 12
    assert with_advantage.additional_damage == 4
    assert without_advantage.damage == 8
    assert without_advantage.additional_damage == 0


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
    assert creature.multiattack is not None
    sequence = creature.multiattack.executable_sequence(
        {
            action.name
            for action in creature.stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )
    assert [invocation.name for invocation in sequence] == [
        "Tentacle",
        "Tentacle",
    ]
    assert isinstance(
        creature.stat_block_actions["Tentacle"],
        AttackActionDefinition,
    )
    assert isinstance(
        creature.stat_block_actions["Consume Memories"],
        SavingThrowActionDefinition,
    )
    dominate = creature.stat_block_actions["Dominate Mind (2/Day)"]
    assert isinstance(dominate, SavingThrowActionDefinition)
    assert dominate.resource == ActionResource(
        kind="uses",
        maximum=2,
        reset="day",
    )
    saving_throw = resolve_saving_throw(
        creature,
        "intelligence",
        15,
        roller=lambda _sides: 10,
    )
    assert saving_throw.modifiers.total == 8

    air_elemental = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "air-elemental",
                "stat_block": {"name": "Air Elemental", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )
    assert air_elemental.attributes.movement.speed_feet == 10
    assert air_elemental.attributes.movement.fly_feet == 90
    assert air_elemental.attributes.movement.effective_speed_feet == 90
    assert air_elemental.attributes.movement.squares_per_turn == 18


def test_xmm_multiattacks_through_azer_sentinel_are_enriched() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    names = [
        "Aboleth",
        "Adult Black Dragon",
        "Adult Blue Dragon",
        "Adult Brass Dragon",
        "Adult Bronze Dragon",
        "Adult Copper Dragon",
        "Adult Gold Dragon",
        "Adult Green Dragon",
        "Adult Red Dragon",
        "Adult Silver Dragon",
        "Adult White Dragon",
        "Air Elemental",
        "Ancient Black Dragon",
        "Ancient Blue Dragon",
        "Ancient Brass Dragon",
        "Ancient Bronze Dragon",
        "Ancient Copper Dragon",
        "Ancient Gold Dragon",
        "Ancient Green Dragon",
        "Ancient Red Dragon",
        "Ancient Silver Dragon",
        "Ancient White Dragon",
        "Animated Armor",
        "Ankylosaurus",
        "Ape",
        "Archelon",
        "Archmage",
        "Assassin",
    ]

    for name in names:
        monster = catalog.find(name, "XMM")
        multiattack = next(
            action for action in monster.action if action.name == "Multiattack"
        )
        assert multiattack.mechanics is not None
        creature = build_creature(
            CreatureSchema.model_validate(
                {
                    "id": name.lower().replace(" ", "-"),
                    "stat_block": {"name": name, "source": "XMM"},
                }
            ),
            bestiary=catalog,
        )
        assert creature.multiattack is not None
        if name != "Assassin":
            assert creature.multiattack.executable_sequence(
                {
                    action.name
                    for action in creature.stat_block_actions.values()
                    if isinstance(action, AttackActionDefinition)
                }
            )

    assassin = catalog.find("Assassin", "XMM")
    assassin_step = assassin.action[0].mechanics.plans[0].steps[0]
    assert isinstance(assassin_step, ChoiceStepSchema)
    assert [option.name for option in assassin_step.options] == [
        "Shortsword",
        "Light Crossbow",
    ]
    assassin_creature = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "assassin",
                "stat_block": {"name": "Assassin", "source": "XMM"},
            }
        ),
        bestiary=catalog,
    )
    assert assassin_creature.multiattack is not None
    assassin_plans = assassin_creature.multiattack.executable_slot_plans(
        {"Shortsword", "Light Crossbow"}
    )
    [assassin_slots] = assassin_plans
    assert len(assassin_slots) == 3
    assert all(
        {option.name for option in slot.options}
        == {"Shortsword", "Light Crossbow"}
        for slot in assassin_slots
    )

    black_dragon = catalog.find("Adult Black Dragon", "XMM")
    black_replacement = (
        black_dragon.action[0].mechanics.plans[0].replacements[0]
    )
    assert black_replacement.options[0].cast_level == 3

    white_dragon = catalog.find("Adult White Dragon", "XMM")
    assert white_dragon.action[0].mechanics.plans[0].replacements == []
    white_creature = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "adult-white-dragon",
                "stat_block": {
                    "name": "Adult White Dragon",
                    "source": "XMM",
                },
            }
        ),
        bestiary=catalog,
    )
    rend = white_creature.stat_block_actions["Rend"]
    assert isinstance(rend, AttackActionDefinition)
    damage = [
        effect for effect in rend.hit if isinstance(effect, DamageEffect)
    ]
    assert damage == [
        DamageEffect("2d6", 6, "slashing"),
        DamageEffect("1d8", 0, "cold"),
    ]
    goblin = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "goblin-target",
                "stat_block": {
                    "name": "Goblin Warrior",
                    "source": "XMM",
                },
            }
        ),
        bestiary=catalog,
    )
    outcome = resolve_attack(
        white_creature,
        goblin,
        attacker_label="Dragon",
        target_label="Goblin",
        preferred_attack_name="Rend",
        d20_roller=lambda _sides: 19,
        dice_roller=lambda count, _sides: count * 2,
    )
    assert outcome.damage == 12
    assert outcome.additional_damage == 2
    assert outcome.additional_damage_details[0]["damage_type"] == "cold"


def test_enriched_multiattack_action_references_have_typed_mechanics() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)
    referenced_actions = []
    for monster in catalog:
        multiattacks = [
            action.mechanics
            for action in monster.action
            if action.mechanics is not None
            and action.mechanics.type == "multiattack"
        ]
        for multiattack in multiattacks:
            for plan in multiattack.plans:
                invocations = []
                for step in plan.steps:
                    invocations.extend(
                        step.options
                        if isinstance(step, ChoiceStepSchema)
                        else [step.invocation]
                    )
                for replacement in plan.replacements:
                    invocations.extend(replacement.options)
                for invocation in invocations:
                    if not isinstance(
                        invocation,
                        StatBlockActionInvocationSchema,
                    ):
                        continue
                    referenced = next(
                        action
                        for action in monster.action
                        if re.sub(
                            r"\s*\{@[^}]+\}",
                            "",
                            action.name,
                        ).strip().casefold()
                        == invocation.name.casefold()
                    )
                    referenced_actions.append(referenced)
                    assert isinstance(
                        referenced.mechanics,
                        (
                            AttackActionMechanicsSchema,
                            SavingThrowActionMechanicsSchema,
                        ),
                    )

    assert len(referenced_actions) == 79

    aboleth = catalog.find("Aboleth", "XMM")
    tentacle = next(action for action in aboleth.action if action.name == "Tentacle")
    grapple = tentacle.mechanics.hit[1]
    assert grapple.condition == "grappled"
    assert grapple.escape_dc == 14
    assert grapple.source_capacity == 4

    dominate = next(
        action
        for action in aboleth.action
        if action.name == "Dominate Mind (2/Day)"
    )
    assert dominate.mechanics.resource.maximum == 2
    assert [
        repeat.trigger
        for repeat in dominate.mechanics.failure[0].repeat_saves
    ] == ["on_damage", "elapsed"]

    ancient_gold = catalog.find("Ancient Gold Dragon", "XMM")
    weakening = next(
        action
        for action in ancient_gold.action
        if action.name == "Weakening Breath"
    )
    assert weakening.mechanics.dc == 24
    assert weakening.mechanics.failure[0].effects[1].dice == "1d10"


def test_b_and_c_monster_actions_have_typed_mechanics() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    actions = [
        action
        for monster in catalog
        if monster.name.startswith(("B", "C"))
        for action in monster.action
    ]

    assert len(actions) == 94
    assert all(action.mechanics is not None for action in actions)


def test_all_typed_stat_block_action_variants_survive_loading() -> None:
    catalog = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    avatar = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "avatar",
                "stat_block": {"name": "Avatar of Death", "source": "DMG"},
            }
        ),
        bestiary=catalog,
    )

    assert isinstance(
        avatar.stat_block_actions["Reaping Scythe"],
        AutomaticActionDefinition,
    )

    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Test Caster",
            "source": "TEST",
            "action": [
                {
                    "name": "Innate Spellcasting",
                    "entries": ["The creature casts a spell."],
                    "mechanics": {
                        "type": "spellcasting",
                        "ability": "cha",
                        "spells": [
                            {
                                "name": "Scorching Ray",
                                "source": "XPHB",
                                "cast_level": 3,
                            }
                        ],
                    },
                }
            ],
        }
    )
    spellcasting = build_stat_block_actions(monster)["Innate Spellcasting"]
    assert isinstance(spellcasting, SpellcastingActionDefinition)
    assert spellcasting.spells[0].name == "Scorching Ray"
    assert spellcasting.spells[0].cast_level == 3


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
    monsters_dir = tmp_path / "monsters"
    monsters_dir.mkdir()
    record = '{"name": "Goblin", "source": "TEST"}'
    (monsters_dir / "goblin-a.json").write_text(record, encoding="utf-8")
    (monsters_dir / "goblin-b.json").write_text(record, encoding="utf-8")

    with pytest.raises(ValueError, match=r"Duplicate content record 'Goblin\\|TEST'"):
        load_bestiary_catalog(tmp_path)
