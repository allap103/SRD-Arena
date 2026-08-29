"""Build the parent ongoing effect and lifecycle for a resolved spell."""

from typing import cast

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.effects.runtime import (
    EndEventRule,
    OngoingEffectLifecycle,
    RepeatedDamage,
    RepeatSaveLifecycle,
)

from ..rules import spell_duration_rounds
from .context import SpellActionContext
from .details import effect_duration_rounds
from .persistent_rules import PersistentRulePlan
from .polarity import persistent_spell_effect_polarity
from .preparation import PreparedSpellResolution
from .scaling import resource_dice_increment, scale_dice
from .targets import ResolvedSpellTargets


def build_ongoing_spell_effect(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    resolved: ResolvedSpellTargets,
    rules: PersistentRulePlan,
) -> EffectResult | None:
    """Create the shared parent when persistent state is required.

    >>> from types import SimpleNamespace
    >>> from ..definitions import Spell
    >>> context = SimpleNamespace(
    ...     spell=Spell("ward", "Ward", "TEST", 1), current_round=1
    ... )
    >>> prepared = SimpleNamespace(
    ...     conditions=(), temporary_hit_point_effects=(), repeat_save=None
    ... )
    >>> resolved = SimpleNamespace(affected_targets=())
    >>> build_ongoing_spell_effect(
    ...     context, prepared, resolved, PersistentRulePlan((), None)
    ... ) is None
    True
    """

    spell = context.spell
    duration_rounds = spell_duration_rounds(spell)
    has_turn_start_temporary_hit_points = any(
        temporary.trigger == "target_turn_start"
        for temporary in prepared.temporary_hit_point_effects
    )
    has_persistent_state = bool(
        prepared.conditions or rules.effects or has_turn_start_temporary_hit_points
    )
    has_lifecycle = bool(
        duration_rounds is not None
        or spell.concentration
        or prepared.repeat_save is not None
    )
    if not resolved.affected_targets or not has_persistent_state or not has_lifecycle:
        return None

    assert context.creature.spellcasting is not None
    parent_kind = "concentration" if spell.concentration else "spell"
    return EffectResult(
        kind="start_ongoing_effect",
        target_ref=resolved.affected_targets[0].target_ref,
        data={
            "effect_kind": parent_kind,
            "source_ref": context.source_ref,
            "polarity": persistent_spell_effect_polarity(prepared).value,
            "source_label": context.creature.name,
            "definition_id": spell.id,
            "recast_ends_previous": spell.recast_ends_previous,
            "target_refs": [target.target_ref for target in resolved.affected_targets],
            "duration_rounds": (
                duration_rounds
                if duration_rounds is not None
                else effect_duration_rounds(rules.duration)
            ),
        },
        effect_label=spell.name,
        lifecycle=_build_lifecycle(context, prepared),
        rule_effects=rules.effects,
    )


def _build_lifecycle(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
) -> OngoingEffectLifecycle:
    """Build repeat saves, end events, and turn-start grants for one casting."""

    assert context.creature.spellcasting is not None
    repeat_save = (
        RepeatSaveLifecycle(
            trigger=prepared.repeat_save.trigger,
            ability=cast(str, prepared.repeat_save.ability),
            dc=context.creature.spellcasting.save_dc,
            failure_conditions=tuple(
                Condition(value) for value in prepared.repeat_failure_conditions
            ),
            failure_damage=tuple(
                RepeatedDamage(
                    cast(
                        str,
                        scale_dice(
                            damage.dice,
                            resource_dice_increment(
                                prepared.definition,
                                "damage_dice",
                                damage.damage_type,
                            ),
                            prepared.levels_above,
                        ),
                    ),
                    damage.damage_type,
                )
                for damage in prepared.repeat_failure_damage
            ),
            damage_grants_advantage=prepared.damage_repeat_save_advantage,
        )
        if prepared.repeat_save is not None
        else None
    )
    return OngoingEffectLifecycle(
        started_round=context.current_round,
        repeat_save=repeat_save,
        end_events=tuple(
            EndEventRule(event, scope) for event, scope in prepared.end_events
        ),
        turn_start_temporary_hit_points=next(
            (
                temporary.value
                + (
                    context.creature.spellcasting.ability_modifier
                    if temporary.modifier == "ability_modifier"
                    else 0
                )
                for temporary in prepared.temporary_hit_point_effects
                if temporary.trigger == "target_turn_start"
            ),
            0,
        ),
    )
