"""Create Stinking Cloud's persistent area and reusable turn-start save."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from srd_arena.domain.effects import (
    ActionEconomyKind,
    ActionProhibition,
    AreaTurnStartSave,
    Condition,
)
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    EffectResult,
    SpellResolutionDetails,
)
from srd_arena.domain.effects.runtime import OngoingEffectLifecycle

from ..properties import spell_duration_rounds
from ..resolution_steps.context import SpellActionContext


def resolve_stinking_cloud(
    context: SpellActionContext,
    resolve_declarative: Callable[[SpellActionContext], ActionResolutionResult],
) -> ActionResolutionResult:
    """Resolve placement, then preserve the cloud independently of occupants."""

    result = resolve_declarative(context)
    details = result.details
    if not isinstance(details, SpellResolutionDetails) or context.area is None:
        return result
    assert context.creature.spellcasting is not None
    area_effect = EffectResult(
        kind="start_ongoing_effect",
        target_ref=context.source_ref,
        data={
            "effect_kind": "concentration",
            "source_ref": context.source_ref,
            "polarity": "harmful",
            "source_label": context.creature.name,
            "definition_id": context.spell.id,
            "target_refs": [],
            "duration_rounds": spell_duration_rounds(context.spell),
            "obscures_vision": STINKING_CLOUD_OBSCURES_VISION,
        },
        effect_label=context.spell.name,
        lifecycle=OngoingEffectLifecycle(
            started_round=context.current_round,
            area_turn_start_save=stinking_cloud_save(
                context.creature.spellcasting.save_dc
            ),
        ),
        area=context.area,
    )
    cast_messages = result.messages[:1] if context.announce_cast else []
    return replace(
        result,
        messages=cast_messages,
        effects=[area_effect],
        details=replace(details, affected_target_refs=(), success=True),
    )


STINKING_CLOUD_OBSCURES_VISION = True


def stinking_cloud_save(save_dc: int) -> AreaTurnStartSave:
    """Share the cloud's mechanical save rule with execution and observation."""
    return AreaTurnStartSave(
        ability="constitution",
        dc=save_dc,
        failure_conditions=(Condition.POISONED,),
        failure_rule_effects=(
            ActionProhibition(
                frozenset(
                    {
                        ActionEconomyKind.ACTION,
                        ActionEconomyKind.BONUS_ACTION,
                    }
                )
            ),
        ),
        negated_by_condition_immunity=Condition.POISONED,
    )
