from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import load_bestiary_catalog
from srd_arena.content.creatures.stat_block_schema import BestiaryMonsterSchema
from srd_arena.content.creatures.actions.schema import (
    CapabilitySchema,
)
from srd_arena.content.creatures.actions.translator import build_stat_block_actions
from srd_arena.content.capabilities import SavingThrowResolutionSchema
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import (
    AttackResolution,
    DerivedDifficultyClass,
    DerivedAttackBonus,
    FixedAttackBonus,
    FixedDifficultyClass,
    LimitedUsePool,
    PoolUseCost,
    RechargePool,
    SavingThrowResolution,
    SpellSlotCost,
)
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    SavingThrowActionDefinition,
    Spellcasting,
    SpellcastingActionDefinition,
)


def test_spells_and_stat_blocks_share_saving_throw_resolution_schema() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fireball = spells.find("Fireball", "XPHB")
    assert fireball.capability is not None
    spell_resolution = fireball.capability.resolution.root

    dragon = monsters.find("Ancient White Dragon", "XMM")
    breath = next(
        action
        for action in dragon.action
        if action.name.startswith("Cold Breath")
    )
    assert isinstance(breath.capability, CapabilitySchema)
    action_resolution = breath.capability.resolution

    assert isinstance(spell_resolution, SavingThrowResolutionSchema)
    assert isinstance(action_resolution, SavingThrowResolutionSchema)
    assert spell_resolution.difficulty.type == "spell_save_dc"
    assert action_resolution.difficulty.type == "fixed"
    assert action_resolution.difficulty.value == 22


def test_spells_and_stat_blocks_compile_shared_domain_capabilities() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fireball = build_spell("Fireball", "XPHB", spells)
    assert fireball.capability is not None
    assert fireball.capability.definition is not None
    spell_resolution = fireball.capability.definition.resolution
    assert isinstance(spell_resolution, SavingThrowResolution)
    assert isinstance(spell_resolution.difficulty, DerivedDifficultyClass)
    assert spell_resolution.difficulty.derivation == "spell_save_dc"

    dragon = monsters.find("Ancient White Dragon", "XMM")
    breath = next(
        definition
        for name, definition in build_stat_block_actions(dragon).items()
        if name.startswith("Cold Breath")
    )
    assert isinstance(breath, SavingThrowActionDefinition)
    assert breath.capability is not None
    action_resolution = breath.capability.resolution
    assert isinstance(action_resolution, SavingThrowResolution)
    assert isinstance(action_resolution.difficulty, FixedDifficultyClass)
    assert action_resolution.difficulty.value == 22


def test_spells_and_stat_blocks_compile_shared_attack_resolutions() -> None:
    spells = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    monsters = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)

    fire_bolt = build_spell("Fire Bolt", "XPHB", spells)
    assert fire_bolt.capability is not None
    assert fire_bolt.capability.definition is not None
    spell_resolution = fire_bolt.capability.definition.resolution
    assert isinstance(spell_resolution, AttackResolution)
    assert isinstance(spell_resolution.attack_bonus, DerivedAttackBonus)
    assert spell_resolution.attack_bonus.derivation == "spell_attack_modifier"

    goblin = monsters.find("Goblin Warrior", "XMM")
    scimitar = build_stat_block_actions(goblin)["Scimitar"]
    assert isinstance(scimitar, AttackActionDefinition)
    assert scimitar.capability is not None
    action_resolution = scimitar.capability.resolution
    assert isinstance(action_resolution, AttackResolution)
    assert isinstance(action_resolution.attack_bonus, FixedAttackBonus)
    assert action_resolution.attack_bonus.value == 4


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


def test_npc_spell_uses_are_separate_from_player_spell_slots() -> None:
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

    spellcasting = build_stat_block_actions(monster)["Spellcasting"]
    assert isinstance(spellcasting, SpellcastingActionDefinition)
    fireball, fire_bolt = spellcasting.spells

    assert isinstance(fireball.resource_pool, LimitedUsePool)
    assert fireball.resource_pool.maximum == 2
    assert fireball.resource_pool.refresh == "day"
    assert isinstance(fireball.cost, PoolUseCost)
    assert fireball.cost.pool_id == fireball.resource_pool.id
    assert fire_bolt.resource_pool is None
    assert fire_bolt.cost is None
