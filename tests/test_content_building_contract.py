import pytest

from srd_arena.content.capabilities import CapabilityBuildError
from srd_arena.content.creatures.actions.builder import (
    build_declared_stat_block_actions,
    build_stat_block_actions,
)
from srd_arena.content.creatures.stat_block_schema import BestiaryMonsterSchema
from srd_arena.content.spells import SpellSchema
from srd_arena.content.spells.building import build_spell_definition


def _ability_check_spell(status: str) -> SpellSchema:
    implementation: dict[str, object] = {"status": status}
    if status == "blocked":
        implementation["blocked_by"] = ["ability-check resolution compilation"]
    return SpellSchema.model_validate(
        {
            "name": "Dispel Magic Example",
            "source": "TEST",
            "level": 3,
            "school": "A",
            "implementation": implementation,
            "capability": {
                "target": {"type": "creature"},
                "resolution": {
                    "type": "ability_check",
                    "ability": "spellcasting",
                    "dc": "ten_plus_spell_level",
                    "success": {"effects": []},
                },
            },
        }
    )


def test_executable_spell_rejects_an_unsupported_structured_resolution() -> None:
    spell = _ability_check_spell("complete")

    with pytest.raises(CapabilityBuildError) as raised:
        build_spell_definition(spell)

    assert raised.value.content == "Spell 'Dispel Magic Example'"
    assert raised.value.location == "capability.resolution"
    assert raised.value.mechanic == "AbilityCheckResolutionSchema"


def test_blocked_spell_keeps_its_structured_draft_without_compiling_it() -> None:
    spell = _ability_check_spell("blocked")

    assert build_spell_definition(spell) is None


def test_action_without_a_capability_is_declared_but_not_executable() -> None:
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Example Monster",
            "source": "TEST",
            "action": [
                {
                    "name": "Unstructured Action",
                    "entries": ["This action has not been structured yet."],
                }
            ],
        }
    )

    assert build_stat_block_actions(monster) == {}
    [declaration] = build_declared_stat_block_actions(monster)
    assert declaration.name == "Unstructured Action"
    assert declaration.capability_type is None
