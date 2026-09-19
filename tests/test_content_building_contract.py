import pytest
from pydantic import ValidationError

from srd_arena.content.creatures.actions.builder import (
    build_declared_stat_block_actions,
    build_stat_block_actions,
)
from srd_arena.content.creatures.stat_block_schema import BestiaryMonsterSchema
from srd_arena.content.spells import SpellSchema
from srd_arena.domain.creatures import StandardActionGrantDefinition


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


def test_schema_rejects_an_unbuildable_resolution() -> None:
    with pytest.raises(ValidationError, match="ability_check"):
        _ability_check_spell("complete")


def test_blocked_status_does_not_admit_an_unbuildable_resolution() -> None:
    with pytest.raises(ValidationError, match="ability_check"):
        _ability_check_spell("blocked")


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


def test_bonus_entry_can_grant_shared_standard_actions() -> None:
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Example Goblin",
            "source": "TEST",
            "bonus": [
                {
                    "name": "Nimble Escape",
                    "entries": ["The goblin takes Disengage or Hide."],
                    "capability": {
                        "type": "standard_action_grant",
                        "actions": ["disengage", "hide"],
                    },
                }
            ],
        }
    )

    definition = build_stat_block_actions(monster)["Nimble Escape"]

    assert isinstance(definition, StandardActionGrantDefinition)
    assert definition.actions == ("disengage", "hide")
    assert definition.economy == "bonus_action"
