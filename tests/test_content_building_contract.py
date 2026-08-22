import pytest
from pydantic import ValidationError

from srd_arena.content.creatures.actions.builder import (
    build_declared_stat_block_actions,
    build_stat_block_actions,
)
from srd_arena.content.creatures.stat_block_schema import BestiaryMonsterSchema
from srd_arena.content.spells import SpellSchema
from srd_arena.content.spells.builder import build_spell_definition


def test_executable_spell_rejects_an_unsupported_structured_resolution() -> None:
    with pytest.raises(ValidationError, match="ability_check"):
        SpellSchema.model_validate(
            {
                "name": "Dispel Magic Example",
                "source": "TEST",
                "level": 3,
                "school": "A",
                "implementation": {"status": "complete"},
                "capability": {
                    "target": {"type": "creature"},
                    "resolution": {
                        "type": "ability_check",
                        "ability": "spellcasting",
                        "dc": "ten_plus_resource_level",
                        "success": {"effects": []},
                    },
                },
            }
        )


def test_blocked_spell_records_omission_without_an_executable_draft() -> None:
    spell = SpellSchema.model_validate(
        {
            "name": "Dispel Magic Example",
            "source": "TEST",
            "level": 3,
            "school": "A",
            "implementation": {
                "status": "blocked",
                "blocked_by": ["ability-check resolution support"],
            },
        }
    )

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
