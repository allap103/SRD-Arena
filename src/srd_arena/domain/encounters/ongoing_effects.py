from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from ..effects.results import EffectResult
from ..effects.runtime import (
    EffectSource,
    EffectSourceKind,
    Indefinite,
    OngoingEffect,
    OngoingEffectKind,
    Rounds,
    RuntimeStateIdentity,
)
from ..rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .models import EncounterProgress


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def start_ongoing_effect(
    state: EncounterState,
    result: EffectResult,
    origin_id: str,
) -> OngoingEffect:
    source_ref = _required_string(result, "source_ref")
    source_label = _required_string(result, "source_label")
    definition_id = _required_string(result, "definition_id")
    kind = OngoingEffectKind(_required_string(result, "effect_kind"))
    if kind is OngoingEffectKind.CONCENTRATION:
        end_concentration(state, source_ref)
    source = EffectSource(
        kind=EffectSourceKind.SPELL,
        definition_id=definition_id,
        applied_by_ref=source_ref,
        label=source_label,
        origin_id=origin_id,
    )
    parameters = result.data.get("parameters")
    duration_rounds = result.data.get("duration_rounds")
    target_refs_data = result.data.get("target_refs")
    target_refs = (
        tuple(ref for ref in target_refs_data if isinstance(ref, str))
        if isinstance(target_refs_data, list)
        else (result.target_ref,)
    )
    effect = OngoingEffect(
        identity=RuntimeStateIdentity(
            id=f"ongoing:{kind.value}:{origin_id}",
            source=source,
        ),
        target_refs=target_refs,
        duration=(
            Rounds(duration_rounds)
            if isinstance(duration_rounds, int)
            else Indefinite()
        ),
        kind=kind,
        parameters=dict(parameters) if isinstance(parameters, dict) else {},
        dispellable=True,
    )
    state.ongoing_effects.append(effect)
    return effect


def end_concentration(state: EncounterState, source_ref: str) -> None:
    origins = {
        effect.identity.source.origin_id
        for effect in state.ongoing_effects
        if effect.kind is OngoingEffectKind.CONCENTRATION
        and effect.identity.source.applied_by_ref == source_ref
    }
    if not origins:
        return
    state.ongoing_effects = [
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.origin_id not in origins
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.identity.source.origin_id not in origins
    ]


def resolve_end_turn_effects(
    state: EncounterState,
    creature_ref: str,
    progress: EncounterProgress | None = None,
) -> None:
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if creature_ref in effect.target_refs
        and effect.parameters.get("repeat_save_trigger") == "end_of_turn"
    )
    for effect in matching:
        ability = effect.parameters.get("save_ability")
        dc = effect.parameters.get("save_dc")
        if not isinstance(ability, str) or not isinstance(dc, int):
            continue
        target = state.creatures[creature_ref].creature
        save = resolve_saving_throw(
            cast(SavingThrowCreature, target),
            cast(Ability, ability),
            dc,
            roller=_roll_die,
            automatic_failure_reasons=(
                state._automatic_save_failure_provider_ids_for(
                    creature_ref,
                    ability,
                )
            ),
        )
        if progress is not None:
            outcome = "succeeds" if save.check.success else "fails"
            progress.messages.append(
                (
                    "system",
                    f"{target.name} {outcome} on the repeated {ability.title()} "
                    f"save against {effect.identity.source.label or 'the effect'}.",
                )
            )
        if save.check.success:
            _remove_effect_target(state, effect, creature_ref)


def expire_ongoing_effects_for_turn_start(
    state: EncounterState,
    creature_ref: str,
) -> None:
    expired = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.applied_by_ref == creature_ref
        and _round_duration_expired(state, effect)
    )
    for effect in expired:
        _remove_effect_tree(state, effect)


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


def resolve_concentration_damage(
    state: EncounterState,
    creature_ref: str,
    damage: int,
    progress: EncounterProgress | None = None,
) -> None:
    if damage <= 0:
        return
    concentrating = next(
        (
            effect
            for effect in state.ongoing_effects
            if effect.kind is OngoingEffectKind.CONCENTRATION
            and effect.identity.source.applied_by_ref == creature_ref
        ),
        None,
    )
    if concentrating is None:
        return
    creature = state.creatures[creature_ref].creature
    if creature.get_health() <= 0:
        end_concentration(state, creature_ref)
        return
    dc = max(10, damage // 2)
    save = resolve_saving_throw(
        cast(SavingThrowCreature, creature),
        "constitution",
        dc,
        roller=_roll_die,
    )
    if progress is not None:
        outcome = "maintains" if save.check.success else "loses"
        progress.messages.append(
            (
                "system",
                f"{creature.name} {outcome} concentration "
                f"(Constitution {save.check.roll.total} vs DC {dc}).",
            )
        )
    if not save.check.success:
        end_concentration(state, creature_ref)


def _remove_effect_tree(state: EncounterState, effect: OngoingEffect) -> None:
    origin_id = effect.identity.source.origin_id
    state.ongoing_effects = [
        existing
        for existing in state.ongoing_effects
        if existing.identity.id != effect.identity.id
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.identity.source.origin_id != origin_id
    ]


def _remove_effect_target(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    remaining_targets = tuple(
        existing for existing in effect.target_refs if existing != target_ref
    )
    state.conditions = [
        condition
        for condition in state.conditions
        if not (
            condition.identity.source.origin_id
            == effect.identity.source.origin_id
            and condition.target_ref == target_ref
        )
    ]
    if not remaining_targets:
        state.ongoing_effects = [
            existing
            for existing in state.ongoing_effects
            if existing.identity.id != effect.identity.id
        ]
        return
    state.ongoing_effects = [
        replace(existing, target_refs=remaining_targets)
        if existing.identity.id == effect.identity.id
        else existing
        for existing in state.ongoing_effects
    ]


def _required_string(result: EffectResult, key: str) -> str:
    value = result.data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Ongoing effect requires string {key}.")
    return value
