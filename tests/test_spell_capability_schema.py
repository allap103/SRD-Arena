import pytest
from pydantic import ValidationError

from srd_arena.content.spells import SpellSchema


def _spell(
    capability: dict[str, object] | None,
    *,
    implementation: dict[str, object] | None = None,
) -> SpellSchema:
    data: dict[str, object] = {
        "name": "Example Spell",
        "source": "XPHB",
        "level": 3,
        "school": "V",
    }
    if capability is not None:
        data["capability"] = capability
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
    assert spell.capability is not None
    capability = spell.capability.model_dump()
    assert capability["resolution"]["success_damage"] == "half"
    assert capability["resolution"]["failure"]["effects"][0]["damage_type"] == "fire"


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
                    "effects": [{"type": "condition", "condition": "paralyzed"}]
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

    assert spell.capability is not None
    capability = spell.capability.model_dump()
    assert capability["target"]["requirements"][0]["creature_types"] == ["humanoid"]
    assert capability["resolution"]["repeat_save"]["trigger"] == "turn_end"


def test_custom_spell_resolver_ids_are_closed_and_require_executable_status() -> None:
    capability = {
        "target": {"type": "creature"},
        "resolution": {
            "type": "saving_throw",
            "ability": "wis",
            "failure": {"effects": []},
        },
    }

    spell = _spell(
        capability,
        implementation={"status": "complete", "resolver": "slow"},
    )

    assert spell.implementation.resolver == "slow"
    with pytest.raises(ValidationError):
        _spell(
            capability,
            implementation={"status": "complete", "resolver": "unknown"},
        )
    with pytest.raises(ValidationError):
        _spell(
            None,
            implementation={"status": "unimplemented", "resolver": "slow"},
        )


@pytest.mark.parametrize(
    "effect_type",
    [
        "ongoing_modifier_group",
        "create_spell_entity",
        "grant_action",
        "create_persistent_area",
        "prevent_defeat",
        "cancel_pending_event",
    ],
)
def test_schema_rejects_effects_without_domain_builders(effect_type: str) -> None:
    with pytest.raises(ValidationError, match=effect_type):
        _spell(
            {
                "target": {"type": "self"},
                "resolution": _automatic({"type": effect_type}),
            },
            implementation={"status": "complete"},
        )


@pytest.mark.parametrize(
    "resolution_type",
    ["ability_check", "contested_check", "hit_point_pool", "choice", "random_table"],
)
def test_schema_rejects_resolutions_without_domain_builders(
    resolution_type: str,
) -> None:
    with pytest.raises(ValidationError, match=resolution_type):
        _spell(
            {
                "target": {"type": "creature"},
                "resolution": {"type": resolution_type},
            },
            implementation={"status": "complete"},
        )


def test_composite_targeting_remains_available_to_custom_resolvers() -> None:
    spell = _spell(
        {
            "target": {
                "type": "composite_area",
                "component": {
                    "geometry": {"shape": "cube", "length_feet": 10},
                    "maximum": 10,
                },
            },
            "resolution": _automatic(),
        },
        implementation={"status": "complete"},
    )

    assert spell.capability is not None
    assert spell.capability.target.type == "composite_area"


def test_triggered_casts_links_interception_and_defeat_prevention_are_typed() -> None:
    spell = _spell(
        {
            "target": {"type": "event_target", "binding": "triggering_target"},
            "casting_trigger": {
                "event": "attack_hit",
                "timing": "immediately_after",
                "requirements": [{"type": "attack_source", "source": "weapon"}],
                "target": {
                    "type": "event_target",
                    "binding": "triggering_target",
                },
            },
            "resolution": _automatic(),
            "outcome_triggers": [
                {
                    "event": "attack_would_hit",
                    "target": {
                        "type": "event_target",
                        "binding": "triggering_attacker",
                    },
                    "resolution": _automatic(),
                }
            ],
        },
        implementation={"status": "complete"},
    )

    assert spell.capability is not None
    assert spell.capability.casting_trigger is not None
    assert spell.capability.casting_trigger.event == "attack_hit"
    assert spell.capability.outcome_triggers[0].event == "attack_would_hit"


def test_implementation_status_cannot_hide_missing_or_extra_capability() -> None:
    with pytest.raises(
        ValidationError, match="Complete spells must define a capability"
    ):
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


def test_schema_rejects_unknown_capability_and_invalid_structures() -> None:
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

    with pytest.raises(ValidationError, match="random_table"):
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
