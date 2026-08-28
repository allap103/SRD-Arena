"""Resolve ongoing effects at turn boundaries."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from ...effects.results import EffectResult
from ...effects.runtime import OngoingEffect, Rounds
from ...rolls.dice import D20RollMode, resolve_dice
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .concentration import resolve_concentration_damage
from .lifecycle_events import resolve_spell_lifecycle_event
from .removal import _remove_effect_target, _remove_effect_tree
from .rolls import roll_die

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..models import EncounterProgress


def has_condition_save_advantage(
    state: EncounterState,
    target_ref: str,
    conditions: tuple[str, ...],
) -> bool:
    """Return whether ongoing state grants advantage against the conditions.

    >>> from types import SimpleNamespace
    >>> effect = SimpleNamespace(
    ...     target_refs=("hero",),
    ...     parameters={"condition_save_advantages": ["Poisoned"]},
    ... )
    >>> state = SimpleNamespace(ongoing_effects=[effect])
    >>> has_condition_save_advantage(state, "hero", ("poisoned",))
    True
    >>> has_condition_save_advantage(state, "other", ("poisoned",))
    False
    """

    requested = {condition.casefold() for condition in conditions}
    if not requested:
        return False
    return any(
        target_ref in effect.target_refs
        and isinstance(configured, list)
        and bool(
            requested.intersection(
                value.casefold() for value in configured if isinstance(value, str)
            )
        )
        for effect in state.ongoing_effects
        for configured in (effect.parameters.get("condition_save_advantages"),)
    )


def resolve_end_turn_effects(
    state: EncounterState,
    creature_ref: str,
    progress: EncounterProgress | None = None,
) -> None:
    """Resolve repeat saves and repeat damage due at a creature's turn end.

    Effects belonging to other creatures or other triggers remain unchanged.

    >>> from types import SimpleNamespace
    >>> effect = SimpleNamespace(
    ...     target_refs=("other",),
    ...     parameters={"repeat_save_trigger": "end_of_turn"},
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
        and effect.parameters.get("repeat_save_trigger") == "end_of_turn"
        and creature_ref not in _progressed_target_refs(effect)
    )
    for effect in matching:
        ability = effect.parameters.get("save_ability")
        dc = effect.parameters.get("save_dc")
        if not isinstance(ability, str) or not isinstance(dc, int):
            continue
        target = state.creatures[creature_ref].creature
        repeat_conditions = effect.parameters.get("repeat_failure_conditions", [])
        save_mode: D20RollMode = (
            "advantage"
            if isinstance(repeat_conditions, list)
            and has_condition_save_advantage(
                state,
                creature_ref,
                tuple(
                    condition
                    for condition in repeat_conditions
                    if isinstance(condition, str)
                ),
            )
            else "normal"
        )
        roll_rules = state.combat_rules.roll_modifiers(
            state,
            creature_ref,
            "saving_throw",
            ability=ability,
        )
        save = resolve_saving_throw(
            cast(SavingThrowCreature, target),
            cast(Ability, ability),
            dc,
            mode=save_mode,
            sourced_modifier_override=roll_rules.resolve_modifier(roll_die),
            sourced_mode_override=roll_rules.mode,
            roller=roll_die,
            automatic_failure_reasons=(
                state._automatic_save_failure_provider_ids_for(
                    creature_ref,
                    ability,
                )
            ),
        )
        effect_label = effect.parameters.get("effect_label")
        if not isinstance(effect_label, str):
            effect_label = effect.identity.source.definition_id.replace(
                "_", " "
            ).title()
        damage_details: list[dict[str, object]] = []
        if progress is not None:
            outcome = "succeeds" if save.check.success else "fails"
            progress.messages.append(
                (
                    "system",
                    f"{target.name} {outcome} on the repeated {ability.title()} "
                    f"save against {effect_label}.",
                )
            )
        if save.check.success:
            _remove_effect_target(state, effect, creature_ref)
        else:
            repeat_damage = effect.parameters.get("repeat_failure_damage", [])
            if isinstance(repeat_damage, list):
                for damage in repeat_damage:
                    if not isinstance(damage, dict):
                        continue
                    dice = damage.get("dice")
                    damage_type = damage.get("damage_type")
                    if not isinstance(dice, str) or not isinstance(damage_type, str):
                        continue
                    count_text, separator, sides_text = dice.partition("d")
                    if (
                        not separator
                        or not count_text.isdigit()
                        or not sides_text.isdigit()
                    ):
                        continue
                    source_ref = effect.identity.source.applied_by_ref
                    damage_modifier = (
                        state.combat_rules.roll_modifiers(
                            state,
                            source_ref,
                            "damage_roll",
                        ).resolve_modifier(roll_die)
                        if source_ref in state.creatures
                        else 0
                    )
                    roll = resolve_dice(
                        int(count_text),
                        int(sides_text),
                        modifier=damage_modifier,
                        roller=roll_die,
                    )
                    applied = target.take_damage(roll.total, damage_type)
                    damage_details.append(
                        {
                            "target_ref": creature_ref,
                            "target_label": target.name,
                            "dice": dice,
                            "dice_values": [die.result for die in roll.dice],
                            "die_rolls": [list(die.rolls) for die in roll.dice],
                            "dice_total": roll.subtotal,
                            "modifier": roll.modifier,
                            "total": roll.total,
                            "damage_type": damage_type,
                            "applied_damage": applied,
                        }
                    )
                    if progress is not None:
                        progress.messages.append(
                            (
                                "system",
                                f"{effect_label} deals "
                                f"{applied} {damage_type} damage to {target.name}.",
                            )
                        )
                    source_ref = effect.identity.source.applied_by_ref or "system"
                    resolve_spell_lifecycle_event(
                        state,
                        "target_damaged",
                        actor_ref=source_ref,
                        target_ref=creature_ref,
                        progress=progress,
                    )
                    resolve_concentration_damage(
                        state,
                        creature_ref,
                        applied,
                        progress,
                    )
            failure_conditions = effect.parameters.get("repeat_failure_conditions", [])
            if isinstance(failure_conditions, list) and failure_conditions:
                state.conditions = [
                    condition
                    for condition in state.conditions
                    if not (
                        condition.identity.source.origin_id
                        == effect.identity.source.origin_id
                        and condition.target_ref == creature_ref
                    )
                ]
                state._apply_effects(
                    [
                        EffectResult(
                            kind="apply_condition",
                            target_ref=creature_ref,
                            data={
                                "condition": condition,
                                "source_ref": (
                                    effect.identity.source.applied_by_ref or "system"
                                ),
                                "source_label": effect.identity.source.label or "Spell",
                                "source_kind": "spell",
                                "definition_id": (effect.identity.source.definition_id),
                                "parent_effect_kind": effect.kind.value,
                            },
                        )
                        for condition in failure_conditions
                        if isinstance(condition, str)
                    ],
                    origin_id=effect.identity.source.origin_id,
                )
                progressed = effect.parameters.get("progressed_target_refs", [])
                progressed_refs = (
                    list(progressed) if isinstance(progressed, list) else []
                )
                progressed_refs.append(creature_ref)
                parameters = dict(effect.parameters)
                parameters["progressed_target_refs"] = progressed_refs
                state.ongoing_effects = [
                    replace(existing, parameters=parameters)
                    if existing.identity.id == effect.identity.id
                    else existing
                    for existing in state.ongoing_effects
                ]
        if progress is not None:
            progress.events.append(
                state._event(
                    "ongoing_effect_resolved",
                    creature_ref=creature_ref,
                    data={
                        "spell_id": effect.identity.source.definition_id,
                        "spell_name": effect_label,
                        "effect_id": effect.identity.id,
                        "save_detail": {
                            "target_ref": creature_ref,
                            "target_label": target.name,
                            "ability": ability,
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


def expire_ongoing_effects_for_turn_start(
    state: EncounterState,
    creature_ref: str,
) -> None:
    """Expire source-owned durations and grant turn-start temporary HP.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock
    >>> source = SimpleNamespace(applied_by_ref="cleric")
    >>> effect = SimpleNamespace(
    ...     identity=SimpleNamespace(source=source),
    ...     target_refs=("hero",),
    ...     parameters={"turn_start_temporary_hit_points": 5},
    ...     duration=SimpleNamespace(),
    ... )
    >>> creature = Mock()
    >>> state = SimpleNamespace(
    ...     ongoing_effects=[effect], round=SimpleNamespace(number=1),
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ... )
    >>> expire_ongoing_effects_for_turn_start(state, "hero")
    >>> creature.grant_temporary_hit_points.call_args.args
    (5,)
    """

    expired = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.applied_by_ref == creature_ref
        and _round_duration_expired(state, effect)
    )
    for effect in expired:
        _remove_effect_tree(state, effect)
    for effect in tuple(state.ongoing_effects):
        if creature_ref not in effect.target_refs:
            continue
        temporary_hit_points = effect.parameters.get("turn_start_temporary_hit_points")
        if isinstance(temporary_hit_points, int) and temporary_hit_points > 0:
            state.creatures[creature_ref].creature.grant_temporary_hit_points(
                temporary_hit_points
            )


def _round_duration_expired(
    state: EncounterState,
    effect: OngoingEffect,
) -> bool:
    started_round = effect.parameters.get("started_round")
    return (
        isinstance(effect.duration, Rounds)
        and isinstance(started_round, int)
        and state.round.number >= started_round + effect.duration.count
    )


def _progressed_target_refs(effect: OngoingEffect) -> tuple[str, ...]:
    value = effect.parameters.get("progressed_target_refs", [])
    if not isinstance(value, list):
        return ()
    return tuple(ref for ref in value if isinstance(ref, str))
