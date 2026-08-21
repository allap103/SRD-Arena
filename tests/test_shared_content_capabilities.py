from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import load_bestiary_catalog
from srd_arena.content.creatures.actions.schema import (
    CapabilitySchema,
)
from srd_arena.content.capabilities import SavingThrowResolutionSchema
from srd_arena.content.spells import load_spell_catalog


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
