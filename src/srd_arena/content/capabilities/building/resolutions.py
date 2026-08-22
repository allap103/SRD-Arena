"""Build domain resolutions from authored resolution schemas."""

from collections.abc import Iterable, Sequence
from typing import Literal, Protocol, cast

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import resolutions
from srd_arena.content.capabilities.schemas.durations import EffectDurationSchema
from .common import build_duration, normalize_ability, resolution_root
from .effects import build_effects
from .errors import CapabilityBuildError
from .requirements import build_checked_requirement


class _SpellRepeatSaveLike(Protocol):
    trigger: str
    ability: str | None
    on_failure: object | None
    successes_required: int
    failures_required: int | None
    counters_need_not_be_consecutive: bool


class _ActionRepeatSaveLike(Protocol):
    trigger: str
    interval_amount: int | None
    interval_unit: Literal["hour", "day"] | None
    distance_from_source_feet: int | None
    effects_end_on_success: bool
    automatic_success_after: EffectDurationSchema | None


class _SaveModifierLike(Protocol):
    roll: str
    mode: str
    ability: str | None
    dice: str | None
    value: int | None
    duration: EffectDurationSchema | None
    requirements: Sequence[object]


def build_resolution(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.CapabilityResolution:
    """Build one executable resolution or identify its unsupported mechanic."""
    if isinstance(value, resolutions.FixedAttackResolutionSchema):
        return _build_attack_resolution(
            modes=value.attack_modes,
            attack_bonus=domain.FixedAttackBonus(value.attack_bonus),
            hit=domain.Outcome(
                build_effects(value.hit, content=content, location=f"{location}.hit")
            ),
        )
    if isinstance(value, resolutions.AttackResolutionSchema):
        return _build_attack_resolution(
            modes=(value.mode,),
            attack_bonus=domain.DerivedAttackBonus("spell_attack_modifier"),
            hit=_build_outcome(value.hit, content=content, location=f"{location}.hit"),
            miss=_build_outcome(
                value.miss,
                content=content,
                location=f"{location}.miss",
            ),
            attacks=value.attacks,
            allocation=value.allocation,
        )
    if isinstance(value, resolutions.AutomaticResolutionSchema):
        return domain.AutomaticResolution(
            _build_outcome(
                value.outcome,
                content=content,
                location=f"{location}.outcome",
            )
        )
    if isinstance(value, resolutions.SavingThrowResolutionSchema):
        return _build_saving_throw(value, content=content, location=location)
    raise CapabilityBuildError(
        content=content,
        location=location,
        mechanic=type(value).__name__,
    )


def _build_saving_throw(
    value: resolutions.SavingThrowResolutionSchema[object, object],
    *,
    content: str,
    location: str,
) -> domain.SavingThrowResolution:
    if value.ability is None:
        raise CapabilityBuildError(
            content=content,
            location=f"{location}.ability",
            mechanic="saving throw without an ability",
        )
    failure_value = value.failure
    if isinstance(failure_value, list):
        failure = tuple(
            domain.OutcomeStage(
                effects=build_effects(
                    stage.effects,
                    content=content,
                    location=f"{location}.failure[{index}].effects",
                ),
                repeat_saves=tuple(
                    _build_repeat_save(item, value.ability, content, location)
                    for item in getattr(stage, "repeat_saves", ())
                ),
            )
            for index, stage in enumerate(failure_value)
        )
    else:
        outcome = _build_outcome(
            failure_value,
            content=content,
            location=f"{location}.failure",
        )
        repeat = getattr(value, "repeat_save", None)
        failure = (
            domain.OutcomeStage(
                outcome.effects,
                (
                    (_build_repeat_save(repeat, value.ability, content, location),)
                    if repeat is not None
                    else ()
                ),
            ),
        )
    return domain.SavingThrowResolution(
        ability=normalize_ability(value.ability) or value.ability,
        difficulty=_build_difficulty(value.difficulty),
        failure=failure,
        success=_build_optional_outcome(
            value.success,
            content=content,
            location=f"{location}.success",
        ),
        always=_build_optional_outcome(
            getattr(value, "always", None),
            content=content,
            location=f"{location}.always",
        ),
        success_damage=value.success_damage,
        automatic_success=tuple(
            build_checked_requirement(
                item,
                content=content,
                location=f"{location}.automatic_success",
            )
            for item in getattr(value, "automatic_success", ())
        ),
        automatic_failure=tuple(
            build_checked_requirement(
                item,
                content=content,
                location=f"{location}.automatic_failure",
            )
            for item in getattr(value, "automatic_failure", ())
        ),
        save_modifiers=tuple(
            _build_save_modifier(
                item,
                content=content,
                location=f"{location}.save_modifiers",
            )
            for item in getattr(value, "save_modifiers", ())
        ),
    )


def _build_outcome(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.Outcome:
    values = tuple(
        getattr(effect, "root", effect) for effect in getattr(value, "effects", ())
    )
    return domain.Outcome(
        build_effects(values, content=content, location=f"{location}.effects"),
        bool(getattr(value, "end_capability", False)),
    )


def _build_optional_outcome(
    value: object | None,
    *,
    content: str,
    location: str,
) -> domain.Outcome:
    if value is None:
        return domain.Outcome()
    return _build_outcome(value, content=content, location=location)


def _build_difficulty(value: object) -> domain.DifficultyClass:
    if isinstance(value, resolutions.FixedDifficultyClassSchema):
        return domain.FixedDifficultyClass(value.value)
    derived = cast(resolutions.DerivedDifficultyClassSchema, value)
    return domain.DerivedDifficultyClass(derived.type)


def _build_repeat_save(
    value: object,
    default_ability: str,
    content: str,
    location: str,
) -> domain.RepeatSave:
    if hasattr(value, "on_failure"):
        spell_repeat = cast(_SpellRepeatSaveLike, value)
        failure_effects: tuple[domain.CapabilityEffect, ...] = ()
        authored_failure = spell_repeat.on_failure
        if authored_failure is not None:
            failure_resolution = resolution_root(authored_failure)
            if not isinstance(
                failure_resolution,
                resolutions.AutomaticResolutionSchema,
            ):
                raise CapabilityBuildError(
                    content=content,
                    location=f"{location}.repeat_save.on_failure",
                    mechanic=type(failure_resolution).__name__,
                )
            failure_effects = _build_outcome(
                failure_resolution.outcome,
                content=content,
                location=f"{location}.repeat_save.on_failure.outcome",
            ).effects
        trigger_aliases = {"turn_end": "end_of_turn", "turn_start": "start_of_turn"}
        trigger = trigger_aliases.get(spell_repeat.trigger, spell_repeat.trigger)
        return domain.RepeatSave(
            trigger=trigger,
            ability=normalize_ability(spell_repeat.ability or default_ability),
            failure_effects=failure_effects,
            successes_required=spell_repeat.successes_required,
            failures_required=spell_repeat.failures_required,
            counters_need_not_be_consecutive=(
                spell_repeat.counters_need_not_be_consecutive
            ),
        )
    action_repeat = cast(_ActionRepeatSaveLike, value)
    return domain.RepeatSave(
        trigger=action_repeat.trigger,
        interval_amount=action_repeat.interval_amount,
        interval_unit=action_repeat.interval_unit,
        distance_from_source_feet=action_repeat.distance_from_source_feet,
        effects_end_on_success=action_repeat.effects_end_on_success,
        automatic_success_after=build_duration(action_repeat.automatic_success_after),
    )


def _build_save_modifier(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.RollModifierEffect:
    modifier = cast(_SaveModifierLike, value)
    return domain.RollModifierEffect(
        roll=modifier.roll,
        mode=modifier.mode,
        ability=normalize_ability(modifier.ability),
        dice=modifier.dice,
        value=modifier.value,
        duration=build_duration(modifier.duration),
        requirements=tuple(
            build_checked_requirement(item, content=content, location=location)
            for item in modifier.requirements
        ),
    )


def _build_attack_resolution(
    *,
    modes: Iterable[Literal["melee", "ranged"]],
    attack_bonus: domain.AttackBonus,
    hit: domain.Outcome,
    miss: domain.Outcome = domain.Outcome(),
    attacks: int = 1,
    allocation: Literal["same_target", "same_or_different"] = "same_target",
) -> domain.AttackResolution:
    return domain.AttackResolution(
        modes=tuple(modes),
        attack_bonus=attack_bonus,
        hit=hit,
        miss=miss,
        attacks=attacks,
        allocation=allocation,
    )
