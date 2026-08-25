"""Translate legacy ongoing-effect parameters into typed rule effects."""

from __future__ import annotations

from typing import cast

from ...effects.modifiers import (
    ModifierMode,
    ModifierSubject,
    RollKind,
    RollModifier,
)
from ...effects.rule_effects import (
    ArmorClassAdjustment,
    RollAdjustment,
    RuntimeRuleEffect,
    SpeedAdjustment,
)


def parse_runtime_rule_effects(
    parameters: dict[str, object],
) -> tuple[RuntimeRuleEffect, ...]:
    """Build typed query contributions from existing serialized parameters."""

    effects: list[RuntimeRuleEffect] = []
    armor_class_modifier = parameters.get("armor_class_modifier")
    if isinstance(armor_class_modifier, int) and armor_class_modifier:
        effects.append(ArmorClassAdjustment(armor_class_modifier))

    speed_modifier = parameters.get("speed_modifier_feet")
    if isinstance(speed_modifier, int) and speed_modifier:
        effects.append(SpeedAdjustment(speed_modifier))

    effects.extend(
        RollAdjustment(modifier)
        for modifier in parse_roll_modifiers(parameters.get("roll_modifiers"))
    )
    return tuple(effects)


def parse_roll_modifiers(value: object) -> tuple[RollModifier, ...]:
    """Parse the serialized roll modifiers currently stored in effect data."""

    if not isinstance(value, list):
        return ()
    return tuple(
        RollModifier(
            roll=cast(RollKind, item["roll"]),
            mode=cast(ModifierMode, item["mode"]),
            dice=cast(str | None, item.get("dice")),
            value=cast(int | None, item.get("value")),
            subject=cast(ModifierSubject, item.get("subject", "target")),
            ignored_by_senses=tuple(
                sense
                for sense in item.get("ignored_by_senses", [])
                if isinstance(sense, str)
            ),
            ability=cast(str | None, item.get("ability")),
        )
        for item in value
        if isinstance(item, dict)
        and item.get("roll")
        in {"ability_check", "attack_roll", "damage_roll", "saving_throw"}
        and item.get("mode")
        in {"advantage", "disadvantage", "add", "subtract"}
    )
