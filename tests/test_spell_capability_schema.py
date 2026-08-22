import pytest
from pydantic import ValidationError

from srd_arena.content.spells import SpellSchema, build_spell


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
    return {"type": "automatic", "outcome": {"effects": list(effects)}}


def test_direct_area_damage_supports_geometry_modifier_and_scaling() -> None:
    spell = _spell(
        {
            "target": {
                "type": "area",
                "origin": "point_in_range",
                "range_feet": 150,
                "geometry": {
                    "shape": "cylinder",
                    "radius_feet": 20,
                    "height_feet": 40,
                },
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
                            "bonus": 2,
                            "modifier": "ability_modifier",
                            "minimum": 3,
                            "damage_type": "fire",
                        }
                    ]
                },
                "success_damage": "half",
            },
            "scaling": [
                {
                    "type": "resource_level",
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
    assert capability["target"]["geometry"]["height_feet"] == 40
    assert capability["resolution"]["failure"]["effects"][0]["modifier"] == (
        "ability_modifier"
    )
    definition = build_spell(spell).definition
    assert definition is not None
    assert definition.target.height_feet == 40
    assert definition.target.affects == "creatures_and_objects"
    damage = definition.resolution.failure[0].effects[0]
    assert damage.modifier == "ability_modifier"
    assert damage.minimum == 3


def test_condition_spell_supports_requirements_and_repeat_save() -> None:
    spell = _spell(
        {
            "target": {
                "type": "creature",
                "range_feet": 60,
                "requirements": [
                    {"type": "creature_type", "creature_types": ["humanoid"]},
                    {"type": "willing"},
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
        },
        implementation={"status": "complete"},
    )

    assert spell.capability is not None
    capability = spell.capability.model_dump()
    assert capability["target"]["requirements"][1]["type"] == "willing"
    assert capability["resolution"]["repeat_save"]["trigger"] == "turn_end"


def test_implementation_status_matches_executable_capability() -> None:
    with pytest.raises(ValidationError, match="Complete spells must define"):
        _spell(None, implementation={"status": "complete"})

    with pytest.raises(ValidationError, match="Blocked spells cannot define"):
        _spell(
            {"target": {"type": "self"}, "resolution": _automatic()},
            implementation={"status": "blocked", "blocked_by": ["unsupported"]},
        )


@pytest.mark.parametrize(
    "resolution_type",
    ["ability_check", "hit_point_pool", "random_table", "choice"],
)
def test_schema_rejects_non_executable_resolution_types(
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


@pytest.mark.parametrize(
    "effect_type",
    ["create_entity", "store_spell", "create_persistent_area", "grant_action"],
)
def test_schema_rejects_non_executable_effect_types(effect_type: str) -> None:
    with pytest.raises(ValidationError, match=effect_type):
        _spell(
            {
                "target": {"type": "self"},
                "resolution": _automatic({"type": effect_type}),
            },
            implementation={"status": "complete"},
        )
