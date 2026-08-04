import pytest
from pydantic import ValidationError

from srd_arena.content.schemas import SpellSchema


def _spell(
    mechanics: dict[str, object] | None,
    *,
    implementation: dict[str, object] | None = None,
) -> SpellSchema:
    data: dict[str, object] = {
        "name": "Example Spell",
        "source": "XPHB",
        "level": 3,
        "school": "V",
    }
    if mechanics is not None:
        data["mechanics"] = mechanics
    if implementation is not None:
        data["implementation"] = implementation
    return SpellSchema.model_validate(data)


def _automatic(*effects: dict[str, object]) -> dict[str, object]:
    return {
        "type": "automatic",
        "outcome": {"effects": list(effects)},
    }


def test_direct_area_damage_supports_half_damage_and_slot_scaling() -> None:
    spell = _spell(
        {
            "target": {
                "type": "area",
                "origin": "point_in_range",
                "geometry": {"shape": "sphere", "radius_feet": 20},
                "affects": "creatures_and_objects",
            },
            "resolution": {
                "type": "saving_throw",
                "ability": "dex",
                "failure": {
                    "effects": [
                        {
                            "type": "damage",
                            "dice": "8d6",
                            "damage_type": "fire",
                        }
                    ]
                },
                "success_damage": "half",
            },
            "scaling": [
                {
                    "type": "slot_level",
                    "above_level": 3,
                    "per_level": [{"type": "damage_dice", "amount": "1d6"}],
                }
            ],
        },
        implementation={
            "status": "partial",
            "omissions": [
                {
                    "mechanic": "flammable object ignition",
                    "reason": "Environmental fire is not modeled yet.",
                }
            ],
        },
    )

    assert spell.executable
    assert spell.mechanics is not None
    mechanics = spell.mechanics.model_dump()
    assert mechanics["resolution"]["success_damage"] == "half"
    assert mechanics["resolution"]["failure"]["effects"][0]["damage_type"] == "fire"


def test_condition_spell_supports_type_requirement_and_repeat_save() -> None:
    spell = _spell(
        {
            "target": {
                "type": "creature",
                "line_of_sight": True,
                "requirements": [
                    {
                        "type": "creature_type",
                        "creature_types": ["humanoid"],
                    }
                ],
            },
            "resolution": {
                "type": "saving_throw",
                "ability": "wis",
                "failure": {
                    "effects": [
                        {"type": "condition", "condition": "paralyzed"}
                    ]
                },
                "repeat_save": {"trigger": "turn_end", "ability": "wis"},
            },
            "scaling": [
                {
                    "type": "slot_level",
                    "above_level": 2,
                    "per_level": [{"type": "target_count", "amount": 1}],
                }
            ],
        },
        implementation={"status": "complete"},
    )

    assert spell.mechanics is not None
    mechanics = spell.mechanics.model_dump()
    assert mechanics["target"]["requirements"][0]["creature_types"] == ["humanoid"]
    assert mechanics["resolution"]["repeat_save"]["trigger"] == "turn_end"


def test_compound_spell_groups_shared_ongoing_modifiers() -> None:
    one_minute = {"type": "timed", "amount": 1, "unit": "minute"}
    spell = _spell(
        {
            "target": {
                "type": "area",
                "origin": "point_in_range",
                "geometry": {"shape": "cube", "length_feet": 40},
                "occupants": "chosen",
                "chosen_count": {"minimum": 1, "maximum": 6},
            },
            "resolution": {
                "type": "saving_throw",
                "ability": "wis",
                "failure": {
                    "effects": [
                        {
                            "type": "ongoing_modifier_group",
                            "modifiers": [
                                {
                                    "type": "speed_multiplier",
                                    "numerator": 1,
                                    "denominator": 2,
                                    "duration": one_minute,
                                },
                                {
                                    "type": "prohibit_reactions",
                                    "duration": one_minute,
                                },
                                {
                                    "type": "attack_action_limit",
                                    "maximum": 1,
                                },
                                {
                                    "type": "action_failure_chance",
                                    "action": "cast_spell",
                                    "percent": 25,
                                    "requirements": [
                                        {
                                            "type": "spell_component",
                                            "component": "somatic",
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                },
                "repeat_save": {"trigger": "turn_end", "ability": "wis"},
            },
        },
        implementation={"status": "complete"},
    )

    assert spell.mechanics is not None
    mechanics = spell.mechanics.model_dump()
    modifiers = mechanics["resolution"]["failure"]["effects"][0]["modifiers"]
    assert [modifier["type"] for modifier in modifiers] == [
        "speed_multiplier",
        "prohibit_reactions",
        "attack_action_limit",
        "action_failure_chance",
    ]


def test_hp_pool_and_random_table_are_first_class_resolutions() -> None:
    hp_pool = _spell(
        {
            "target": {
                "type": "area",
                "origin": "point_in_range",
                "geometry": {"shape": "sphere", "radius_feet": 20},
            },
            "resolution": {
                "type": "hit_point_pool",
                "dice": "5d8",
                "on_covered": {
                    "effects": [
                        {"type": "condition", "condition": "unconscious"}
                    ]
                },
            },
        },
        implementation={"status": "complete"},
    )
    random = _spell(
        {
            "target": {"type": "creature"},
            "resolution": {
                "type": "random_table",
                "die": "1d4",
                "entries": [
                    {"minimum": 1, "maximum": 1, "resolution": _automatic()},
                    {"minimum": 2, "maximum": 3, "resolution": _automatic()},
                    {"minimum": 4, "maximum": 4, "resolution": _automatic()},
                ],
            },
        },
        implementation={"status": "complete"},
    )

    assert hp_pool.mechanics is not None
    assert hp_pool.mechanics.model_dump()["resolution"]["cost"] == "current_hit_points"
    assert random.mechanics is not None
    assert len(random.mechanics.model_dump()["resolution"]["entries"]) == 3


def test_granted_actions_and_persistent_areas_share_spell_instance_state() -> None:
    spell = _spell(
        {
            "target": {"type": "self"},
            "casting_requirements": [{"type": "free_hand"}],
            "resolution": _automatic(
                {
                    "type": "create_spell_entity",
                    "entity_id": "flame_blade",
                    "entity_kind": "weapon",
                    "actions": [
                        {
                            "id": "attack",
                            "label": "Attack with Flame Blade",
                            "economy": "magic_action",
                            "target": {"type": "creature"},
                            "resolution": {
                                "type": "spell_attack",
                                "mode": "melee",
                                "hit": {
                                    "effects": [
                                        {
                                            "type": "damage",
                                            "dice": "3d6",
                                            "damage_type": "fire",
                                        }
                                    ]
                                },
                            },
                        }
                    ],
                },
                {
                    "type": "grant_action",
                    "action": {
                        "id": "recreate_blade",
                        "label": "Recreate Flame Blade",
                        "economy": "bonus_action",
                        "target": {"type": "self"},
                        "resolution": _automatic(),
                    },
                },
            ),
        },
        implementation={"status": "complete"},
    )

    assert spell.mechanics is not None
    effects = spell.mechanics.model_dump()["resolution"]["outcome"]["effects"]
    assert effects[0]["actions"][0]["id"] == "attack"
    assert effects[1]["action"]["economy"] == "bonus_action"


def test_composite_and_moving_areas_are_explicit() -> None:
    fire_storm = _spell(
        {
            "target": {
                "type": "composite_area",
                "component": {
                    "geometry": {"shape": "cube", "length_feet": 10},
                    "maximum": 10,
                },
                "contiguity": "edge_or_corner",
            },
            "resolution": _automatic(),
        },
        implementation={"status": "complete"},
    )
    cloudkill = _spell(
        {
            "target": {
                "type": "area",
                "origin": "point_in_range",
                "geometry": {"shape": "sphere", "radius_feet": 20},
            },
            "resolution": _automatic(
                {
                    "type": "create_persistent_area",
                    "properties": [{"type": "obscurement", "degree": "heavy"}],
                    "triggers": [
                        {
                            "event": "creature_turn_start",
                            "resolution": _automatic(
                                {
                                    "type": "damage",
                                    "dice": "5d8",
                                    "damage_type": "poison",
                                }
                            ),
                            "per_target_limit": 1,
                            "limit_period": "turn",
                        }
                    ],
                    "movement": {
                        "trigger": "source_turn_start",
                        "distance_feet": 10,
                        "direction": "away_from_source",
                    },
                    "ends_on": ["strong_wind"],
                }
            ),
        },
        implementation={"status": "complete"},
    )

    assert fire_storm.mechanics is not None
    fire_storm_mechanics = fire_storm.mechanics.model_dump()
    assert fire_storm_mechanics["target"]["component"]["maximum"] == 10
    assert cloudkill.mechanics is not None
    cloudkill_mechanics = cloudkill.mechanics.model_dump()
    area = cloudkill_mechanics["resolution"]["outcome"]["effects"][0]
    assert area["movement"]["distance_feet"] == 10


def test_triggered_casts_links_interception_and_defeat_prevention_are_typed() -> None:
    spell = _spell(
        {
            "target": {"type": "event_target", "binding": "triggering_target"},
            "casting_trigger": {
                "event": "attack_hit",
                "timing": "immediately_after",
                "requirements": [
                    {"type": "attack_source", "source": "weapon"}
                ],
                "target": {
                    "type": "event_target",
                    "binding": "triggering_target",
                },
            },
            "resolution": _automatic(
                {"type": "relationship", "relationship": "marked"},
                {
                    "type": "prevent_defeat",
                    "replacement_hit_points": 1,
                    "uses": 1,
                },
            ),
            "outcome_triggers": [
                {
                    "event": "attack_would_hit",
                    "target": {
                        "type": "event_target",
                        "binding": "triggering_attacker",
                    },
                    "resolution": _automatic(
                        {"type": "cancel_pending_event", "event": "attack"}
                    ),
                }
            ],
        },
        implementation={"status": "complete"},
    )

    assert spell.mechanics is not None
    assert spell.mechanics.casting_trigger is not None
    assert spell.mechanics.casting_trigger.event == "attack_hit"
    assert spell.mechanics.outcome_triggers[0].event == "attack_would_hit"


def test_implementation_status_cannot_hide_missing_or_extra_mechanics() -> None:
    with pytest.raises(ValidationError, match="Complete spells must define mechanics"):
        _spell(None, implementation={"status": "complete"})

    with pytest.raises(ValidationError, match="Unimplemented spells cannot define"):
        _spell(
            {"target": {"type": "self"}, "resolution": _automatic()},
        )

    with pytest.raises(ValidationError, match="must list omissions"):
        _spell(
            {"target": {"type": "self"}, "resolution": _automatic()},
            implementation={"status": "partial"},
        )


def test_schema_rejects_unknown_mechanics_and_invalid_structures() -> None:
    with pytest.raises(ValidationError):
        _spell(
            {
                "target": {"type": "self"},
                "resolution": _automatic({"type": "interpret_prose"}),
            },
            implementation={"status": "complete"},
        )

    with pytest.raises(ValidationError, match="requires length_feet and width_feet"):
        _spell(
            {
                "target": {
                    "type": "area",
                    "origin": "self",
                    "geometry": {"shape": "line", "length_feet": 100},
                },
                "resolution": _automatic(),
            },
            implementation={"status": "complete"},
        )

    with pytest.raises(ValidationError, match="contiguous and non-overlapping"):
        _spell(
            {
                "target": {"type": "creature"},
                "resolution": {
                    "type": "random_table",
                    "die": "1d4",
                    "entries": [
                        {"minimum": 1, "maximum": 1, "resolution": _automatic()},
                        {"minimum": 3, "maximum": 4, "resolution": _automatic()},
                    ],
                },
            },
            implementation={"status": "complete"},
        )
