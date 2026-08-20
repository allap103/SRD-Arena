from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from ..effects.results import EffectResult
from ..effects.modifiers import ModifierMode, ModifierSubject, RollKind, RollModifier
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
from ..rolls.dice import D20RollMode, resolve_dice

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
    if bool(result.data.get("recast_ends_previous", False)):
        previous = tuple(
            effect
            for effect in state.ongoing_effects
            if effect.identity.source.definition_id == definition_id
            and effect.identity.source.applied_by_ref == source_ref
        )
        for effect in previous:
            _remove_effect_tree(state, effect)
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
    maximum_hit_point_modifier = effect.parameters.get("maximum_hit_point_modifier")
    also_modify_current = bool(
        effect.parameters.get("also_modify_current_hit_points", False)
    )
    if isinstance(maximum_hit_point_modifier, int) and maximum_hit_point_modifier:
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_maximum_health_modifier(
                definition_id,
                origin_id,
                maximum_hit_point_modifier,
                also_modify_current=also_modify_current,
            )
    damage_resistances = effect.parameters.get("damage_resistances", [])
    if isinstance(damage_resistances, list):
        for target_ref in effect.target_refs:
            for damage_type in damage_resistances:
                if isinstance(damage_type, str):
                    state.creatures[target_ref].creature.add_damage_resistance(
                        damage_type, origin_id
                    )
    roll_modifiers = effect.parameters.get("roll_modifiers", [])
    if isinstance(roll_modifiers, list):
        parsed = tuple(
            RollModifier(
                roll=cast(RollKind, value["roll"]),
                mode=cast(ModifierMode, value["mode"]),
                dice=cast(str | None, value.get("dice")),
                value=cast(int | None, value.get("value")),
                subject=cast(ModifierSubject, value.get("subject", "target")),
            )
            for value in roll_modifiers
            if isinstance(value, dict)
            and value.get("roll")
            in {"ability_check", "attack_roll", "damage_roll", "saving_throw"}
            and value.get("mode") in {"advantage", "disadvantage", "add", "subtract"}
        )
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_roll_modifiers(
                definition_id, origin_id, parsed
            )
    armor_class_modifier = effect.parameters.get("armor_class_modifier")
    if isinstance(armor_class_modifier, int) and armor_class_modifier:
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_armor_class_modifier(
                definition_id, origin_id, armor_class_modifier
            )
    return effect


def has_condition_save_advantage(
    state: EncounterState,
    target_ref: str,
    conditions: tuple[str, ...],
) -> bool:
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


def end_concentration(state: EncounterState, source_ref: str) -> None:
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.kind is OngoingEffectKind.CONCENTRATION
        and effect.identity.source.applied_by_ref == source_ref
    )
    for effect in matching:
        _remove_effect_tree(state, effect)


def remove_ongoing_effects(state: EncounterState, result: EffectResult) -> None:
    effect_id = result.data.get("effect_id")
    effect_kind = result.data.get("effect_kind")
    parameter = result.data.get("parameter")
    remove_all = bool(result.data.get("all", False))
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if result.target_ref in effect.target_refs
        and (not isinstance(effect_id, str) or effect.identity.id == effect_id)
        and (not isinstance(effect_kind, str) or effect.kind.value == effect_kind)
        and (
            parameter != "negative_maximum_hit_points"
            or (
                isinstance(
                    maximum_modifier := effect.parameters.get(
                        "maximum_hit_point_modifier"
                    ),
                    int,
                )
                and maximum_modifier < 0
            )
        )
    )
    for effect in matching if remove_all else matching[:1]:
        _remove_effect_target(state, effect, result.target_ref)


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
        save = resolve_saving_throw(
            cast(SavingThrowCreature, target),
            cast(Ability, ability),
            dc,
            mode=save_mode,
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
                    roll = resolve_dice(
                        int(count_text),
                        int(sides_text),
                        roller=_roll_die,
                    )
                    applied = target.take_damage(roll.total)
                    if progress is not None:
                        progress.messages.append(
                            (
                                "system",
                                f"{effect.identity.source.label or 'The effect'} deals "
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
                                "definition_id": effect.identity.source.definition_id,
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


def resolve_spell_lifecycle_event(
    state: EncounterState,
    event: str,
    *,
    actor_ref: str,
    target_ref: str | None = None,
    progress: EncounterProgress | None = None,
) -> None:
    for effect in tuple(state.ongoing_effects):
        affected_ref = (
            target_ref
            if event in {"target_damaged", "adjacent_creature_wakes_target"}
            and target_ref is not None
            else actor_ref
        )
        if affected_ref not in effect.target_refs:
            continue
        if event == "target_damaged" and effect.parameters.get(
            "damage_repeat_save_advantage"
        ):
            ability = effect.parameters.get("save_ability")
            dc = effect.parameters.get("save_dc")
            if isinstance(ability, str) and isinstance(dc, int):
                creature = state.creatures[affected_ref].creature
                save = resolve_saving_throw(
                    cast(SavingThrowCreature, creature),
                    cast(Ability, ability),
                    dc,
                    mode="advantage",
                    roller=_roll_die,
                    automatic_failure_reasons=(
                        state._automatic_save_failure_provider_ids_for(
                            affected_ref, ability
                        )
                    ),
                )
                if save.check.success:
                    _remove_effect_target(state, effect, affected_ref)
                    if progress is not None:
                        progress.messages.append(
                            (
                                "system",
                                f"{creature.name} ends "
                                f"{effect.identity.source.label} after taking damage.",
                            )
                        )
                    continue
        end_events = effect.parameters.get("end_events", [])
        if not isinstance(end_events, list):
            continue
        for configured in end_events:
            if not isinstance(configured, list) or len(configured) != 2:
                continue
            configured_event, scope = configured
            if configured_event != event:
                continue
            source_ref = effect.identity.source.applied_by_ref
            if (
                scope == "source_team"
                and source_ref is not None
                and state._creatures_are_opponents(source_ref, actor_ref)
            ):
                continue
            _remove_effect_target(state, effect, affected_ref)
            break


def _remove_effect_tree(state: EncounterState, effect: OngoingEffect) -> None:
    origin_id = effect.identity.source.origin_id
    for target_ref in effect.target_refs:
        _remove_maximum_hit_point_modifier(state, effect, target_ref)
        _remove_damage_resistances(state, effect, target_ref)
        state.creatures[target_ref].creature.remove_roll_modifiers(
            effect.identity.source.definition_id, origin_id
        )
        state.creatures[target_ref].creature.remove_armor_class_modifier(
            effect.identity.source.definition_id, origin_id
        )
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
    _remove_maximum_hit_point_modifier(state, effect, target_ref)
    _remove_damage_resistances(state, effect, target_ref)
    state.creatures[target_ref].creature.remove_roll_modifiers(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_armor_class_modifier(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    remaining_targets = tuple(
        existing for existing in effect.target_refs if existing != target_ref
    )
    state.conditions = [
        condition
        for condition in state.conditions
        if not (
            condition.identity.source.origin_id == effect.identity.source.origin_id
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


def _remove_maximum_hit_point_modifier(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    modifier = effect.parameters.get("maximum_hit_point_modifier")
    if not isinstance(modifier, int) or modifier == 0:
        return
    state.creatures[target_ref].creature.remove_maximum_health_modifier(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
        also_modify_current=bool(
            effect.parameters.get("also_modify_current_hit_points", False)
        ),
    )


def _remove_damage_resistances(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    values = effect.parameters.get("damage_resistances", [])
    if not isinstance(values, list):
        return
    for damage_type in values:
        if isinstance(damage_type, str):
            state.creatures[target_ref].creature.remove_damage_resistance(
                damage_type, effect.identity.source.origin_id
            )


def _progressed_target_refs(effect: OngoingEffect) -> tuple[str, ...]:
    value = effect.parameters.get("progressed_target_refs", [])
    if not isinstance(value, list):
        return ()
    return tuple(ref for ref in value if isinstance(ref, str))


def _required_string(result: EffectResult, key: str) -> str:
    value = result.data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Ongoing effect requires string {key}.")
    return value
