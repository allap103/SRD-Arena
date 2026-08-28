import pytest
from pydantic import ValidationError

from srd_arena.content.capabilities import (
    ConditionEffectSchema,
    ConditionRequirementSchema,
    CreatureTargetSchema,
    DamageEffectSchema,
    TimedDurationSchema,
)
from srd_arena.content.capabilities.requirements import (
    AttackRollModeRequirementSchema,
)
from srd_arena.content.creatures import BestiaryActionSchema
from srd_arena.content.creatures.actions.schema import (
    AttackCapabilitySchema,
    CapabilitySchema,
    SavingThrowActionResolutionSchema,
    SpellcastingCapabilitySchema,
)


def test_attack_action_supports_multiple_hit_effects() -> None:
    action = BestiaryActionSchema.model_validate(
        {
            "name": "Rend",
            "entries": ["Original prose remains authoritative."],
            "capability": {
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

    assert isinstance(action.capability, AttackCapabilitySchema)
    first_effect, second_effect = action.capability.hit
    assert isinstance(first_effect, DamageEffectSchema)
    assert isinstance(second_effect, DamageEffectSchema)
    assert [first_effect.damage_type, second_effect.damage_type] == [
        "slashing",
        "cold",
    ]


def test_damage_effect_supports_attack_roll_mode_requirement() -> None:
    action = BestiaryActionSchema.model_validate(
        {
            "name": "Scimitar",
            "capability": {
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

    assert isinstance(action.capability, AttackCapabilitySchema)
    conditional_damage = action.capability.hit[1]
    assert isinstance(conditional_damage, DamageEffectSchema)
    assert isinstance(
        conditional_damage.requirements[0],
        AttackRollModeRequirementSchema,
    )
    assert conditional_damage.requirements[0].type == "attack_roll_mode"
    assert conditional_damage.requirements[0].mode == "advantage"


def test_save_action_supports_target_requirements_and_half_damage() -> None:
    action = CapabilitySchema.model_validate(
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
            "resolution": {
                "type": "saving_throw",
                "ability": "int",
                "difficulty": {"type": "fixed", "value": 16},
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
                "always": {
                    "effects": [
                        {
                            "type": "gain_memories",
                            "requirement": {
                                "type": "creature_type",
                                "creature_types": ["humanoid"],
                            },
                            "trigger": "reduced_to_zero_by_action",
                        }
                    ]
                },
                "success": {"effects": []},
            },
        }
    )

    assert isinstance(action.target, CreatureTargetSchema)
    requirement = action.target.requirements[0]
    assert isinstance(requirement, ConditionRequirementSchema)
    assert requirement.applied_by == "source"
    assert isinstance(action.resolution, SavingThrowActionResolutionSchema)
    assert action.resolution.success_damage == "half"
    assert action.resolution.always.effects[0].type == "gain_memories"


def test_save_action_supports_staged_failures_and_repeat_saves() -> None:
    action = CapabilitySchema.model_validate(
        {
            "target": {
                "type": "area",
                "shape": "cone",
                "size_feet": 60,
            },
            "resolution": {
                "type": "saving_throw",
                "ability": "con",
                "difficulty": {"type": "fixed", "value": 20},
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
                "success": {"effects": []},
            },
        }
    )

    assert isinstance(action.resolution, SavingThrowActionResolutionSchema)
    assert len(action.resolution.failure) == 2
    repeat = action.resolution.failure[1].repeat_saves[0]
    duration = repeat.automatic_success_after
    assert isinstance(duration, TimedDurationSchema)
    assert duration.amount == 1


def test_condition_duration_can_end_at_start_of_source_turn() -> None:
    action = AttackCapabilitySchema.model_validate(
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

    effect = action.hit[0]
    assert isinstance(effect, ConditionEffectSchema)
    assert effect.duration is not None
    assert effect.duration.type == "start_of_turn"


def test_spellcasting_action_is_distinct_from_save_and_attack_actions() -> None:
    action = SpellcastingCapabilitySchema.model_validate(
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


def test_action_capability_reject_unknown_effects() -> None:
    with pytest.raises(ValidationError):
        CapabilitySchema.model_validate(
            {
                "target": {
                    "type": "creature",
                    "range_feet": 30,
                },
                "resolution": {
                    "type": "saving_throw",
                    "ability": "wis",
                    "difficulty": {"type": "fixed", "value": 16},
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
                    "success": {"effects": []},
                },
            }
        )
