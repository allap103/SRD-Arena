"""Runtime support checks for authored stat-block action definitions."""

from __future__ import annotations

from ...capabilities import ConditionEffect, DamageEffect
from ...creatures.stat_block_actions import (
    AttackActionDefinition,
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
)
from ...effects.conditions import Condition


def stat_block_action_runtime_issue(definition: object) -> str | None:
    """Describe why a stat-block action cannot run in the current engine."""
    if isinstance(definition, AttackActionDefinition):
        for effect in definition.hit:
            if isinstance(effect, DamageEffect):
                continue
            if isinstance(effect, ConditionEffect):
                try:
                    Condition(effect.condition)
                except ValueError:
                    return (
                        f"Condition '{effect.condition}' is not supported by "
                        "the condition runtime yet."
                    )
                if effect.condition != "grappled" and effect.requirements:
                    return (
                        "Conditional attack-applied conditions are not "
                        "executable yet."
                    )
                if effect.condition != "grappled" and effect.ends_on:
                    return (
                        "Event-ended attack-applied conditions are not "
                        "executable yet."
                    )
                if effect.duration is not None and effect.duration.kind not in {
                    "start_of_turn",
                    "end_of_turn",
                }:
                    return (
                        f"Condition duration '{effect.duration.kind}' is not "
                        "executable for attack actions yet."
                    )
                continue
            return (
                f"{type(effect).__name__} is not executable for attack "
                "actions yet."
            )
        return None
    if isinstance(definition, AutomaticActionDefinition):
        effects = definition.effects
    elif isinstance(definition, SavingThrowActionDefinition):
        if len(definition.failure) != 1:
            return "Staged saving-throw failures are not executable yet."
        if definition.failure[0].repeat_saves:
            return "Repeated saving throws are not executable yet."
        if definition.target.kind == "area" and definition.target.origin != "self":
            return "Point-origin stat-block areas are not executable yet."
        effects = (
            *definition.failure[0].effects,
            *definition.success,
            *definition.always,
        )
    else:
        return "This stat-block action type is not executable yet."
    unsupported = next(
        (effect for effect in effects if not isinstance(effect, DamageEffect)),
        None,
    )
    if unsupported is not None:
        return (
            f"{type(unsupported).__name__} is not executable for "
            "stat-block actions yet."
        )
    return None
