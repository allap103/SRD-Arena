"""Compose Slow from reusable, source-aware combat-rule effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from srd_arena.domain.effects.modifiers import RollModifier
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    EffectResult,
    SpellResolutionDetails,
)
from srd_arena.domain.effects.rule_effects import (
    ActionEconomyKind,
    ActionEconomyRestriction,
    ArmorClassAdjustment,
    AttackLimit,
    InvocationFailureChance,
    ReactionProhibition,
    RollAdjustment,
    SpeedMultiplier,
)
from srd_arena.domain.effects.runtime import OngoingEffectLifecycle, RepeatSaveLifecycle

from ..properties import spell_duration_rounds
from ..resolution_steps.context import SpellActionContext


def resolve_slow(
    context: SpellActionContext,
    resolve_declarative: Callable[[SpellActionContext], ActionResolutionResult],
) -> ActionResolutionResult:
    """Resolve common targeting/saves, then attach Slow's grouped rule state.

    A casting that affects no targets retains only its declarative result.

    >>> from types import SimpleNamespace
    >>> result = ActionResolutionResult("slow", "Slow", [], [])
    >>> context = SimpleNamespace()
    >>> resolve_slow(context, lambda current: result) is result
    True
    """

    result = resolve_declarative(context)
    details = result.details
    if not isinstance(details, SpellResolutionDetails):
        return result
    affected_target_refs = details.affected_target_refs
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
        },
        effect_label=context.spell.name,
        lifecycle=OngoingEffectLifecycle(
            started_round=context.current_round,
            repeat_save=RepeatSaveLifecycle(
                trigger="end_of_turn",
                ability="wisdom",
                dc=context.creature.spellcasting.save_dc,
            ),
        ),
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
    return replace(
        result,
        effects=[*result.effects, slow_effect],
        details=replace(details, success=True),
    )
