import pytest
from pydantic import ValidationError

from srd_arena.content.creatures.action_schema import (
    AttackActionMechanicsSchema,
    SavingThrowActionMechanicsSchema,
    SpellcastingActionMechanicsSchema,
)
from srd_arena.content.creatures import BestiaryActionSchema


def test_attack_action_supports_multiple_hit_effects() -> None:
    action = BestiaryActionSchema.model_validate(
        {
            "name": "Rend",
            "entries": ["Original prose remains authoritative."],
            "mechanics": {
                "type": "attack",
                "attack_modes": ["melee"],
                "attack_bonus": 11,
                "reach_feet": 10,
                "target": {
                    "type": "creature",
                    "range_feet": 10,
                },
                "hit": [
                    {
                        "type": "damage",
                        "dice": "2d6",
                        "bonus": 6,
                        "damage_type": "slashing",
                    },
                    {
                        "type": "damage",
                        "dice": "1d8",
                        "damage_type": "cold",
                    },
                ],
            },
        }
    )

    assert isinstance(action.mechanics, AttackActionMechanicsSchema)
    assert [effect.damage_type for effect in action.mechanics.hit] == [
        "slashing",
        "cold",
    ]


def test_damage_effect_supports_attack_roll_mode_requirement() -> None:
    action = BestiaryActionSchema.model_validate(
        {
            "name": "Scimitar",
            "mechanics": {
                "type": "attack",
                "attack_modes": ["melee"],
                "attack_bonus": 4,
                "reach_feet": 5,
                "target": {"type": "creature", "range_feet": 5},
                "hit": [
                    {
                        "type": "damage",
                        "dice": "1d6",
                        "bonus": 2,
                        "damage_type": "slashing",
                    },
                    {
                        "type": "damage",
                        "dice": "1d4",
                        "damage_type": "slashing",
                        "requirements": [
                            {
                                "type": "attack_roll_mode",
                                "mode": "advantage",
                            }
                        ],
                    },
                ],
            },
        }
    )

    assert isinstance(action.mechanics, AttackActionMechanicsSchema)
    conditional_damage = action.mechanics.hit[1]
    assert conditional_damage.requirements[0].type == "attack_roll_mode"
    assert conditional_damage.requirements[0].mode == "advantage"


def test_save_action_supports_target_requirements_and_half_damage() -> None:
    action = SavingThrowActionMechanicsSchema.model_validate(
        {
            "target": {
                "type": "creature",
                "range_feet": 30,
                "requirements": [
                    {
                        "type": "condition",
                        "conditions": ["charmed", "grappled"],
                        "match": "any",
                        "applied_by": "source",
                    }
                ],
            },
            "ability": "int",
            "dc": 16,
            "failure": [
                {
                    "effects": [
                        {
                            "type": "damage",
                            "dice": "3d6",
                            "damage_type": "psychic",
                        }
                    ]
                }
            ],
            "success_damage": "half",
            "always": [
                {
                    "type": "gain_memories",
                    "requirement": {
                        "type": "creature_type",
                        "creature_types": ["humanoid"],
                    },
                    "trigger": "reduced_to_zero_by_action",
                }
            ],
        }
    )

    assert action.target.requirements[0].applied_by == "source"
    assert action.success_damage == "half"
    assert action.always[0].type == "gain_memories"


def test_save_action_supports_staged_failures_and_repeat_saves() -> None:
    action = SavingThrowActionMechanicsSchema.model_validate(
        {
            "target": {
                "type": "area",
                "shape": "cone",
                "size_feet": 60,
            },
            "ability": "con",
            "dc": 20,
            "failure": [
                {
                    "effects": [
                        {
                            "type": "condition",
                            "condition": "incapacitated",
                            "duration": {
                                "type": "end_of_turn",
                                "creature": "target",
                                "turn_offset": 1,
                            },
                        }
                    ],
                    "repeat_saves": [{"trigger": "end_of_turn"}],
                },
                {
                    "effects": [
                        {
                            "type": "condition",
                            "condition": "paralyzed",
                        }
                    ],
                    "repeat_saves": [
                        {
                            "trigger": "end_of_turn",
                            "automatic_success_after": {
                                "type": "timed",
                                "amount": 1,
                                "unit": "minute",
                            },
                        }
                    ],
                },
            ],
        }
    )

    assert len(action.failure) == 2
    assert action.failure[1].repeat_saves[0].automatic_success_after.amount == 1


def test_condition_duration_can_end_at_start_of_source_turn() -> None:
    action = AttackActionMechanicsSchema.model_validate(
        {
            "attack_modes": ["melee"],
            "attack_bonus": 7,
            "target": {"type": "creature", "range_feet": 5},
            "reach_feet": 5,
            "hit": [
                {
                    "type": "condition",
                    "condition": "poisoned",
                    "duration": {
                        "type": "start_of_turn",
                        "creature": "source",
                        "turn_offset": 1,
                    },
                }
            ],
        }
    )

    assert action.hit[0].duration.type == "start_of_turn"


def test_spellcasting_action_is_distinct_from_save_and_attack_actions() -> None:
    action = SpellcastingActionMechanicsSchema.model_validate(
        {
            "ability": "cha",
            "spells": [
                {
                    "name": "Scorching Ray",
                    "source": "XPHB",
                    "cast_level": 3,
                    "uses": "at_will",
                }
            ],
        }
    )

    assert action.type == "spellcasting"
    assert action.spells[0].cast_level == 3


def test_action_mechanics_reject_unknown_effects() -> None:
    with pytest.raises(ValidationError):
        SavingThrowActionMechanicsSchema.model_validate(
            {
                "target": {
                    "type": "creature",
                    "range_feet": 30,
                },
                "ability": "wis",
                "dc": 16,
                "failure": [
                    {
                        "effects": [
                            {
                                "type": "unstructured_prose",
                                "text": "Do something complicated.",
                            }
                        ]
                    }
                ],
            }
        )
