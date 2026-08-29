"""Resolve repeat saves attached to ongoing effects."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.effects.runtime import OngoingEffect
from srd_arena.domain.rolls.dice import D20RollMode
from srd_arena.domain.rolls.saving_throws import Ability, resolve_saving_throw

from ..rule_queries.defenses import has_condition_save_advantage
from ..rule_queries.rolls import roll_modifiers
from ..state_combat import automatic_save_failure_provider_ids_for
from ..state_runtime import apply_encounter_effects, create_event
from .removal import _remove_effect_target
from .repeat_damage import resolve_repeat_failure_damage

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def resolve_end_turn_effects(
    state: EncounterState,
    creature_ref: str,
    progress: EncounterProgress | None = None,
) -> None:
    """Resolve repeat saves and their failure consequences at turn end.

    Effects belonging to other creatures or other triggers remain unchanged.

    >>> from types import SimpleNamespace
    >>> repeat = SimpleNamespace(
    ...     trigger="end_of_turn", progressed_target_refs=frozenset()
    ... )
    >>> effect = SimpleNamespace(
    ...     target_refs=("other",),
    ...     lifecycle=SimpleNamespace(repeat_save=repeat),
    ... )
    >>> state = SimpleNamespace(ongoing_effects=[effect])
    >>> resolve_end_turn_effects(state, "hero")
    >>> state.ongoing_effects == [effect]
    True
    """

    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if creature_ref in effect.target_refs
        and effect.lifecycle.repeat_save is not None
        and effect.lifecycle.repeat_save.trigger == "end_of_turn"
        and creature_ref not in _progressed_target_refs(effect)
    )
    for effect in matching:
        _resolve_repeat_save(state, effect, creature_ref, progress)


def _resolve_repeat_save(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
    progress: EncounterProgress | None,
) -> None:
    repeat_save = effect.lifecycle.repeat_save
    assert repeat_save is not None
    target = state.creatures[creature_ref].creature
    save_mode: D20RollMode = (
        "advantage"
        if has_condition_save_advantage(
            state,
            creature_ref,
            tuple(condition.value for condition in repeat_save.failure_conditions),
        )
        else "normal"
    )
    roll_rules = roll_modifiers(
        state,
        creature_ref,
        "saving_throw",
        ability=repeat_save.ability,
    )
    save = resolve_saving_throw(
        target,
        cast(Ability, repeat_save.ability),
        repeat_save.dc,
        mode=save_mode,
        sourced_modifier_override=roll_rules.resolve_modifier(state.dice.roll_die),
        sourced_mode_override=roll_rules.mode,
        roller=state.dice.roll_die,
        automatic_failure_reasons=automatic_save_failure_provider_ids_for(
            state,
            creature_ref,
            repeat_save.ability,
        ),
    )
    effect_label = (
        effect.label or effect.identity.source.definition_id.replace("_", " ").title()
    )
    if progress is not None:
        outcome = "succeeds" if save.check.success else "fails"
        progress.messages.append(
            (
                "system",
                f"{target.name} {outcome} on the repeated "
                f"{repeat_save.ability.title()} save against {effect_label}.",
            )
        )
    damage_details: list[dict[str, object]] = []
    if save.check.success:
        _remove_effect_target(state, effect, creature_ref)
    else:
        damage_details = resolve_repeat_failure_damage(
            state, effect, creature_ref, target, progress
        )
        _reapply_failure_conditions(state, effect, creature_ref)
    if progress is not None:
        progress.events.append(
            create_event(
                state,
                "ongoing_effect_resolved",
                creature_ref=creature_ref,
                data={
                    "spell_id": effect.identity.source.definition_id,
                    "spell_name": effect_label,
                    "effect_id": effect.identity.id,
                    "save_detail": {
                        "target_ref": creature_ref,
                        "target_label": target.name,
                        "ability": repeat_save.ability,
                        "die": save.check.roll.selected,
                        "dice": list(save.check.roll.dice),
                        "selected_index": save.check.roll.selected_index,
                        "modifier": save.modifiers.total,
                        "total": save.check.roll.total,
                        "target_dc": save.check.target,
                        "success": save.check.success,
                        "automatic_failure_reasons": list(
                            save.automatic_failure_reasons
                        ),
                    },
                    "damage_roll_details": damage_details,
                },
            )
        )


def _reapply_failure_conditions(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
) -> None:
    repeat_save = effect.lifecycle.repeat_save
    assert repeat_save is not None
    if not repeat_save.failure_conditions:
        return
    state.conditions = [
        condition
        for condition in state.conditions
        if not (
            condition.identity.source.origin_id == effect.identity.source.origin_id
            and condition.target_ref == creature_ref
        )
    ]
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref=creature_ref,
                data={
                    "condition": condition.value,
                    "source_ref": (effect.identity.source.applied_by_ref or "system"),
                    "source_label": effect.identity.source.label or "Spell",
                    "source_kind": "spell",
                    "definition_id": effect.identity.source.definition_id,
                    "parent_effect_kind": effect.kind.value,
                },
            )
            for condition in repeat_save.failure_conditions
        ],
        origin_id=effect.identity.source.origin_id,
    )
    progressed_refs = repeat_save.progressed_target_refs.union({creature_ref})
    state.ongoing_effects = [
        replace(
            existing,
            lifecycle=replace(
                existing.lifecycle,
                repeat_save=replace(
                    repeat_save,
                    progressed_target_refs=progressed_refs,
                ),
            ),
        )
        if existing.identity.id == effect.identity.id
        else existing
        for existing in state.ongoing_effects
    ]


def _progressed_target_refs(effect: OngoingEffect) -> tuple[str, ...]:
    repeat_save = effect.lifecycle.repeat_save
    if repeat_save is None:
        return ()
    return tuple(repeat_save.progressed_target_refs)
