"""Compose Slow from reusable, source-aware combat-rule effects."""

from __future__ import annotations

from dataclasses import replace

from ...creatures.feature_rules.types import CapabilityActionResult
from ...effects.modifiers import RollModifier
from ...effects.results import EffectResult
from ...effects.rule_effects import (
    ActionEconomyKind,
    ActionEconomyRestriction,
    ArmorClassAdjustment,
    AttackLimit,
    InvocationFailureChance,
    ReactionProhibition,
    RollAdjustment,
    SpeedMultiplier,
)
from ..properties import spell_duration_rounds
from ..resolution_steps.context import SpellActionContext
from .types import DeclarativeSpellResolver


def resolve_slow(
    context: SpellActionContext,
    resolve_declarative: DeclarativeSpellResolver,
) -> CapabilityActionResult:
    """Resolve common targeting/saves, then attach Slow's grouped rule state."""

    result = resolve_declarative(context)
    affected_target_refs = _affected_target_refs(result)
    if not affected_target_refs:
        return result

    assert context.creature.spellcasting is not None
    slow_effect = EffectResult(
        kind="start_ongoing_effect",
        target_ref=affected_target_refs[0],
        data={
            "effect_kind": "concentration",
            "source_ref": context.source_ref,
            "polarity": "harmful",
            "source_label": context.creature.name,
            "definition_id": context.spell.id,
            "target_refs": list(affected_target_refs),
            "duration_rounds": spell_duration_rounds(context.spell),
            "parameters": {
                "effect_label": context.spell.name,
                "started_round": context.current_round,
                "repeat_save_trigger": "end_of_turn",
                "save_ability": "wisdom",
                "save_dc": context.creature.spellcasting.save_dc,
                "repeat_failure_conditions": [],
                "repeat_failure_damage": [],
            },
        },
        rule_effects=(
            SpeedMultiplier(1, 2),
            ArmorClassAdjustment(-2),
            RollAdjustment(
                RollModifier(
                    roll="saving_throw",
                    mode="subtract",
                    value=2,
                    ability="dexterity",
                )
            ),
            ReactionProhibition(),
            ActionEconomyRestriction(
                frozenset(
                    {
                        ActionEconomyKind.ACTION,
                        ActionEconomyKind.BONUS_ACTION,
                    }
                )
            ),
            AttackLimit(1),
            InvocationFailureChance(
                invocation_kinds=frozenset({"cast_spell"}),
                required_components=frozenset({"somatic"}),
                numerator=1,
                denominator=4,
                code="slow.somatic_spell_failure",
                message="The spell fails because its gestures are too slow.",
            ),
        ),
    )
    details = dict(result.details)
    details["success"] = True
    return replace(
        result,
        effects=[*result.effects, slow_effect],
        details=details,
    )


def _affected_target_refs(
    result: CapabilityActionResult,
) -> tuple[str, ...]:
    value = result.details.get("affected_target_refs")
    if not isinstance(value, list):
        return ()
    return tuple(target_ref for target_ref in value if isinstance(target_ref, str))
