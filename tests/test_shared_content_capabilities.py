from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import load_bestiary_catalog
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
    SavingThrowResolution,
)
from srd_arena.domain.creatures import AttackActionDefinition, SavingThrowActionDefinition


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
