from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import load_bestiary_catalog
from srd_arena.content.creatures.stat_block_schema import BestiaryMonsterSchema
from srd_arena.content.creatures.actions.schema import (
    CapabilitySchema,
)
from srd_arena.content.creatures.actions.builder import build_stat_block_actions
from srd_arena.content.capabilities import (
    AreaTargetSchema,
    CapabilitySchemaBase,
    ResourceScalingSchema,
    SavingThrowResolutionSchema,
    build_capability,
)
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import (
    AttackResolution,
    DerivedDifficultyClass,
    DerivedAttackBonus,
    FixedAttackBonus,
    FixedDifficultyClass,
    HealingEffect,
    LimitedUsePool,
    PoolUseCost,
    RechargePool,
    SavingThrowResolution,
    SpellSlotCost,
)
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
    Spellcasting,
    SpellcastingActionDefinition,
)


def test_non_spell_action_can_use_shared_healing_effect() -> None:
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Test Healer",
            "source": "TEST",
            "action": [
                {
                    "name": "Restore",
                    "capability": {
                        "type": "capability",
                        "target": {"type": "creature", "range_feet": 30},
                        "resolution": {
                            "type": "automatic",
                            "outcome": {
                                "effects": [{"type": "healing", "dice": "1d8"}]
                            },
                        },
                    },
                }
            ],
        }
    )

    restore = build_stat_block_actions(monster)["Restore"]

    assert isinstance(restore, AutomaticActionDefinition)
    assert restore.effects == (HealingEffect(dice="1d8"),)


def test_spells_and_stat_blocks_share_saving_throw_resolution_schema() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fireball = spells.find("Fireball", "XPHB")
    assert fireball.capability is not None
    spell_resolution = fireball.capability.resolution.root

    dragon = monsters.find("Ancient White Dragon", "XMM")
    breath = next(
        action for action in dragon.action if action.name.startswith("Cold Breath")
    )
    assert isinstance(breath.capability, CapabilitySchema)
    action_resolution = breath.capability.resolution

    assert isinstance(spell_resolution, SavingThrowResolutionSchema)
    assert isinstance(action_resolution, SavingThrowResolutionSchema)
    assert spell_resolution.difficulty.type == "spell_save_dc"
    assert action_resolution.difficulty.type == "fixed"
    assert action_resolution.difficulty.value == 22


def test_executable_spell_schema_builds_through_shared_capability_api() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    fireball = spells.find("Fireball", "XPHB")
    assert fireball.capability is not None

    capability = fireball.capability
    assert isinstance(capability, CapabilitySchemaBase)
    assert isinstance(capability.target, AreaTargetSchema)
    assert isinstance(capability.scaling[0], ResourceScalingSchema)

    definition = build_capability(
        target=capability.target,
        resolution=capability.resolution,
        content="Fireball test",
        condition_selection=capability.condition_application,
        scaling_rules=capability.scaling,
        triggers=capability.outcome_triggers,
    )

    assert definition == build_spell(fireball).definition


def test_spells_and_stat_blocks_build_shared_domain_capabilities() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fireball = build_spell(spells.find("Fireball", "XPHB"))
    assert fireball.definition is not None
    spell_resolution = fireball.definition.resolution
    assert isinstance(spell_resolution, SavingThrowResolution)
    assert isinstance(spell_resolution.difficulty, DerivedDifficultyClass)
    assert spell_resolution.difficulty.derivation == "spell_save_dc"
    assert fireball.definition.target.kind == "area"
    assert fireball.definition.target.shape == "sphere"
    assert fireball.definition.target.size_feet == 20

    dragon = monsters.find("Ancient White Dragon", "XMM")
    breath = next(
        definition
        for name, definition in build_stat_block_actions(dragon).items()
        if name.startswith("Cold Breath")
    )
    assert isinstance(breath, SavingThrowActionDefinition)
    assert breath.grant is not None
    action_resolution = breath.grant.definition.resolution
    assert isinstance(action_resolution, SavingThrowResolution)
    assert isinstance(action_resolution.difficulty, FixedDifficultyClass)
    assert action_resolution.difficulty.value == 22


def test_spells_and_stat_blocks_build_shared_attack_resolutions() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fire_bolt = build_spell(spells.find("Fire Bolt", "XPHB"))
    assert fire_bolt.definition is not None
    spell_resolution = fire_bolt.definition.resolution
    assert isinstance(spell_resolution, AttackResolution)
    assert isinstance(spell_resolution.attack_bonus, DerivedAttackBonus)
    assert spell_resolution.attack_bonus.derivation == "spell_attack_modifier"
    assert fire_bolt.definition.target.kind == "creature"
    assert fire_bolt.definition.target.disposition == "any"

    goblin = monsters.find("Goblin Warrior", "XMM")
    scimitar = build_stat_block_actions(goblin)["Scimitar"]
    assert isinstance(scimitar, AttackActionDefinition)
    assert scimitar.grant is not None
    action_resolution = scimitar.grant.definition.resolution
    assert isinstance(action_resolution, AttackResolution)
    assert isinstance(action_resolution.attack_bonus, FixedAttackBonus)
    assert action_resolution.attack_bonus.value == 4


def test_spell_area_selection_compiles_into_shared_target() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    sleep = build_spell(spells.find("Sleep", "XPHB"))

    assert sleep.definition is not None
    assert sleep.definition.target.kind == "area"
    assert sleep.definition.target.occupants == "chosen"
    assert sleep.definition.target.count.minimum == 0
    assert sleep.definition.target.count.maximum == "all"


def test_spell_repetition_and_scaling_build_into_shared_definition() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)

    scorching_ray = build_spell(spells.find("Scorching Ray", "XPHB"))
    eldritch_blast = build_spell(spells.find("Eldritch Blast", "XPHB"))

    assert scorching_ray.definition is not None
    assert scorching_ray.definition.repetition is not None
    assert scorching_ray.definition.repetition.count == 3
    resource_scaling = next(
        scaling
        for scaling in scorching_ray.definition.scaling
        if scaling.basis == "resource_level"
    )
    assert resource_scaling.per_level[0].kind == "projectile_count"
    assert resource_scaling.per_level[0].amount == 1

    assert eldritch_blast.definition is not None
    actor_scaling = next(
        scaling
        for scaling in eldritch_blast.definition.scaling
        if scaling.basis == "actor_level"
        and any(
            increment.kind == "projectile_count"
            for threshold in scaling.thresholds
            for increment in threshold.increments
        )
    )
    assert [threshold.minimum_level for threshold in actor_scaling.thresholds] == [
        1,
        5,
        11,
        17,
    ]


def test_stat_block_resources_belong_to_capability_grants() -> None:
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    dragon = monsters.find("Ancient White Dragon", "XMM")
    breath = next(
        definition
        for name, definition in build_stat_block_actions(dragon).items()
        if name.startswith("Cold Breath")
    )
    assert isinstance(breath, SavingThrowActionDefinition)
    assert breath.grant is not None
    assert isinstance(breath.grant.cost, PoolUseCost)
    assert isinstance(breath.resource_pool, RechargePool)
    assert breath.grant.cost.pool_id == breath.resource_pool.id
    assert breath.resource_pool.die_sides == 6
    assert breath.resource_pool.minimum == 5

    aboleth = monsters.find("Aboleth", "XMM")
    dominate = build_stat_block_actions(aboleth)["Dominate Mind (2/Day)"]
    assert isinstance(dominate, SavingThrowActionDefinition)
    assert isinstance(dominate.resource_pool, LimitedUsePool)
    assert dominate.resource_pool.maximum == 2
    assert dominate.resource_pool.refresh == "day"


def test_spell_slot_cost_is_separate_from_spell_slot_pool() -> None:
    spellcasting = Spellcasting(
        ability="int",
        ability_modifier=4,
        save_dc=15,
        attack_bonus=7,
        caster_progression="full",
        spell_slots_max={1: 4, 2: 3},
    )
    pool = spellcasting.spell_slot_pool
    cost = SpellSlotCost(pool.id, minimum_level=1)

    assert pool.maximum_by_level == ((1, 4), (2, 3))
    assert cost.pool_id == pool.id
    assert cost.allow_higher_level


def test_spell_grants_describe_activation_and_slot_cost() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    spellcasting = Spellcasting(
        ability="int",
        ability_modifier=4,
        save_dc=15,
        attack_bonus=7,
        caster_progression="full",
        spell_slots_max={1: 4, 2: 3, 3: 2},
    )

    fireball = build_spell(spells.find("Fireball", "XPHB"))
    fireball_grant = spellcasting.grant_for(fireball)
    assert fireball_grant is not None
    assert fireball.activation == "action"
    assert fireball_grant.activation == "action"
    assert isinstance(fireball_grant.cost, SpellSlotCost)
    assert fireball_grant.cost.minimum_level == 3

    fire_bolt = build_spell(spells.find("Fire Bolt", "XPHB"))
    fire_bolt_grant = spellcasting.grant_for(fire_bolt)
    assert fire_bolt_grant is not None
    assert fire_bolt.activation == "action"
    assert fire_bolt_grant.cost is None


def test_npc_spell_uses_are_separate_from_player_spell_slots() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Test Mage",
            "source": "TEST",
            "action": [
                {
                    "name": "Spellcasting",
                    "capability": {
                        "type": "spellcasting",
                        "ability": "int",
                        "spells": [
                            {
                                "name": "Fireball",
                                "source": "XPHB",
                                "cast_level": 3,
                                "uses": 2,
                            },
                            {
                                "name": "Fire Bolt",
                                "source": "XPHB",
                                "uses": "at_will",
                            },
                        ],
                    },
                }
            ],
        }
    )

    spellcasting = build_stat_block_actions(monster, spells)["Spellcasting"]
    assert isinstance(spellcasting, SpellcastingActionDefinition)
    fireball, fire_bolt = spellcasting.spells

    assert isinstance(fireball.resource_pool, LimitedUsePool)
    assert fireball.resource_pool.maximum == 2
    assert fireball.resource_pool.refresh == "day"
    assert fireball.spell is not None
    assert fireball.spell.name == "Fireball"
    assert fireball.spell.definition is not None
    assert fireball.grant is not None
    assert fireball.grant.definition == fireball.spell.definition
    assert isinstance(fireball.grant.cost, PoolUseCost)
    assert fireball.grant.cost.pool_id == fireball.resource_pool.id
    assert fire_bolt.resource_pool is None
    assert fire_bolt.spell is not None
    assert fire_bolt.grant is not None
    assert fire_bolt.grant.cost is None
