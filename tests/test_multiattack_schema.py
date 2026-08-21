import pytest
from pydantic import ValidationError

from srd_arena.content.creatures.actions.multiattack import (
    MultiattackCapabilitySchema,
)
from srd_arena.content.creatures import BestiaryActionSchema, BestiaryMonsterSchema


def _action(name: str) -> dict[str, str]:
    return {"type": "stat_block_action", "name": name}


def test_repeated_action_multiattack_is_compact() -> None:
    effect = MultiattackCapabilitySchema.model_validate(
        {
            "plans": [
                {
                    "steps": [
                        {
                            "type": "invoke",
                            "invocation": _action("Slam"),
                            "times": 2,
                        }
                    ]
                }
            ]
        }
    )

    step = effect.plans[0].steps[0]
    assert step.times == 2
    assert step.invocation.name == "Slam"


def test_repeated_choice_supports_any_combination() -> None:
    effect = MultiattackCapabilitySchema.model_validate(
        {
            "plans": [
                {
                    "steps": [
                        {
                            "type": "choose",
                            "options": [
                                _action("Scimitar"),
                                _action("Shortbow"),
                            ],
                            "times": 2,
                        }
                    ]
                }
            ]
        }
    )

    step = effect.plans[0].steps[0]
    assert [option.name for option in step.options] == [
        "Scimitar",
        "Shortbow",
    ]


def test_alternative_plans_and_strict_sequences_are_supported() -> None:
    effect = MultiattackCapabilitySchema.model_validate(
        {
            "plans": [
                {
                    "ordering": "strict",
                    "steps": [
                        {
                            "type": "invoke",
                            "invocation": _action("Claws"),
                        },
                        {
                            "type": "invoke",
                            "invocation": _action("Tail"),
                        },
                    ],
                },
                {
                    "steps": [
                        {
                            "type": "invoke",
                            "invocation": _action("Hurl Flame"),
                            "times": 2,
                        }
                    ]
                },
            ]
        }
    )

    assert len(effect.plans) == 2
    assert effect.plans[0].ordering == "strict"


def test_replacement_can_invoke_action_or_specific_spell() -> None:
    action = BestiaryActionSchema.model_validate(
        {
            "name": "Multiattack",
            "entries": ["Source text remains unchanged."],
            "capability": {
                "type": "multiattack",
                "plans": [
                    {
                        "steps": [
                            {
                                "type": "invoke",
                                "invocation": _action("Rend"),
                                "times": 3,
                            }
                        ],
                        "replacements": [
                            {
                                "target": {
                                    "type": "action",
                                    "name": "Rend",
                                },
                                "options": [
                                    _action("Sleep Breath"),
                                    {
                                        "type": "cast_spell",
                                        "spell": {
                                            "name": "Scorching Ray",
                                            "source": "XPHB",
                                        },
                                        "cast_level": 2,
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        }
    )

    assert action.capability is not None
    replacement = action.capability.plans[0].replacements[0]
    assert replacement.target.name == "Rend"
    assert replacement.options[1].spell.name == "Scorching Ray"


def test_required_and_dynamic_multiattacks_are_supported() -> None:
    effect = MultiattackCapabilitySchema.model_validate(
        {
            "plans": [
                {
                    "requirement": {
                        "type": "action_used_this_turn",
                        "action": "Hasten",
                    },
                    "steps": [
                        {
                            "type": "invoke",
                            "invocation": _action("Slam"),
                            "times": {
                                "type": "creature_stat",
                                "stat": "heads",
                            },
                        }
                    ],
                },
                {
                    "steps": [
                        {
                            "type": "invoke",
                            "invocation": _action("Rend"),
                            "times": {
                                "type": "half_spell_level",
                                "round": "down",
                            },
                        }
                    ]
                },
            ]
        }
    )

    assert effect.plans[0].requirement.action == "Hasten"
    assert effect.plans[0].steps[0].times.stat == "heads"
    assert effect.plans[1].steps[0].times.type == "half_spell_level"


def test_multiattack_schema_rejects_unknown_invocation_types() -> None:
    with pytest.raises(ValidationError):
        MultiattackCapabilitySchema.model_validate(
            {
                "plans": [
                    {
                        "steps": [
                            {
                                "type": "invoke",
                                "invocation": {
                                    "type": "unstructured_prose",
                                    "name": "Something",
                                },
                            }
                        ]
                    }
                ]
            }
        )


def test_multiattack_schema_rejects_condition_as_requirement_alias() -> None:
    with pytest.raises(ValidationError):
        MultiattackCapabilitySchema.model_validate(
            {
                "plans": [
                    {
                        "condition": {
                            "type": "action_used_this_turn",
                            "action": "Hasten",
                        },
                        "steps": [
                            {
                                "type": "invoke",
                                "invocation": _action("Slam"),
                            }
                        ],
                    }
                ]
            }
        )


def test_bestiary_action_rejects_obsolete_multiattack_key() -> None:
    with pytest.raises(
        ValidationError,
        match="Use 'capability' instead",
    ):
        BestiaryActionSchema.model_validate(
            {
                "name": "Multiattack",
                "srdArenaMultiattack": {
                    "plans": [
                        {
                            "steps": [
                                {
                                    "type": "invoke",
                                    "invocation": _action("Slam"),
                                }
                            ]
                        }
                    ]
                },
            }
        )


def test_monster_validates_multiattack_references_across_sections() -> None:
    monster = BestiaryMonsterSchema.model_validate(
        {
            "name": "Test Dragon",
            "source": "TEST",
            "action": [
                {
                    "name": "Multiattack",
                    "capability": {
                        "type": "multiattack",
                        "plans": [
                            {
                                "steps": [
                                    {
                                        "type": "invoke",
                                        "invocation": _action("Rend"),
                                        "times": 3,
                                    }
                                ],
                                "replacements": [
                                    {
                                        "target": {
                                            "type": "action",
                                            "name": "Rend",
                                        },
                                        "options": [
                                            _action("Sleep Breath"),
                                            {
                                                "type": "cast_spell",
                                                "spell": {
                                                    "name": "Scorching Ray",
                                                    "source": "XPHB",
                                                },
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                },
                {"name": "Rend"},
                {"name": "Sleep Breath {@recharge 5}"},
            ],
            "spellcasting": [{"name": "Spellcasting"}],
        }
    )

    assert monster.action[0].capability is not None


def test_monster_rejects_missing_multiattack_reference() -> None:
    with pytest.raises(
        ValidationError,
        match="references missing action entry 'Missing Attack'",
    ):
        BestiaryMonsterSchema.model_validate(
            {
                "name": "Broken Monster",
                "source": "TEST",
                "action": [
                    {
                        "name": "Multiattack",
                        "capability": {
                            "type": "multiattack",
                            "plans": [
                                {
                                    "steps": [
                                        {
                                            "type": "invoke",
                                            "invocation": _action(
                                                "Missing Attack"
                                            ),
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                ],
            }
        )
