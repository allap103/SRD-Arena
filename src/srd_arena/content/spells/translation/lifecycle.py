from srd_arena.content.capabilities import ConditionEffectSchema, DamageEffectSchema
from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    SavingThrowResolutionSchema,
)
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.content.spells.targeting import (
    ConditionImmunityRequirementSchema,
    CreatureTraitRequirementSchema,
)
from srd_arena.domain.spells import SpellDamage

UNIT_ROUNDS = {
    "round": 1,
    "minute": 10,
    "hour": 600,
    "day": 14400,
}


def spell_duration_rounds(raw: SpellSchema) -> int | None:
    for entry in raw.duration:
        duration = entry.get("duration")
        if not isinstance(duration, dict):
            continue
        unit = duration.get("type")
        amount = duration.get("amount")
        if isinstance(unit, str) and isinstance(amount, int) and unit in UNIT_ROUNDS:
            return amount * UNIT_ROUNDS[unit]
    return None


def effect_duration_rounds(duration: object) -> int | None:
    if duration is None:
        return None
    duration_type = getattr(duration, "type", None)
    if duration_type in {"start_of_turn", "end_of_turn"}:
        return 1
    if duration_type != "timed":
        return None
    amount = getattr(duration, "amount", None)
    unit = getattr(duration, "unit", None)
    return (
        amount * UNIT_ROUNDS[unit]
        if isinstance(amount, int)
        and isinstance(unit, str)
        and unit in UNIT_ROUNDS
        else None
    )


def repeat_save_trigger(resolution: object) -> str | None:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return None
    if resolution.repeat_save is None:
        return None
    aliases = {"turn_end": "end_of_turn", "turn_start": "start_of_turn"}
    return aliases.get(resolution.repeat_save.trigger, resolution.repeat_save.trigger)


def repeat_failure_conditions(resolution: object) -> tuple[str, ...]:
    failure = _repeat_failure(resolution)
    if failure is None:
        return ()
    return tuple(
        effect.root.condition
        for effect in failure.outcome.effects
        if isinstance(effect.root, ConditionEffectSchema)
    )


def repeat_failure_damage(resolution: object) -> tuple[SpellDamage, ...]:
    failure = _repeat_failure(resolution)
    if failure is None:
        return ()
    return tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in failure.outcome.effects
        if isinstance(effect.root, DamageEffectSchema)
    )


def _repeat_failure(
    resolution: object,
) -> AutomaticResolutionSchema | None:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return None
    repeat = resolution.repeat_save
    if repeat is None or repeat.on_failure is None:
        return None
    failure = repeat.on_failure.root
    return failure if isinstance(failure, AutomaticResolutionSchema) else None


def end_events(raw: SpellSchema) -> tuple[tuple[str, str], ...]:
    if raw.capability is None:
        return ()
    events: list[tuple[str, str]] = []
    for trigger in raw.capability.outcome_triggers:
        resolution = trigger.resolution.root
        if not isinstance(resolution, AutomaticResolutionSchema):
            continue
        if not resolution.outcome.end_spell:
            continue
        scope = "any"
        if any(
            getattr(requirement, "type", None) == "relationship"
            and getattr(requirement, "relationship", None) == "ally_of_source"
            for requirement in trigger.requirements
        ):
            scope = "source_team"
        events.append((trigger.event, scope))
    return tuple(events)


def damage_repeat_save_advantage(raw: SpellSchema) -> bool:
    if raw.capability is None:
        return False
    return any(
        trigger.event == "target_damaged"
        and isinstance(trigger.resolution.root, SavingThrowResolutionSchema)
        and any(
            modifier.mode == "advantage"
            for modifier in trigger.resolution.root.save_modifiers
        )
        for trigger in raw.capability.outcome_triggers
    )


def save_advantage_against_opponents(resolution: object) -> bool:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return False
    return any(
        modifier.mode == "advantage"
        and any(
            getattr(requirement, "type", None) == "relationship"
            and getattr(requirement, "relationship", None) == "fighting_source_team"
            for requirement in modifier.requirements
        )
        for modifier in resolution.save_modifiers
    )


def automatic_success_condition_immunities(
    resolution: object,
) -> tuple[str, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    return tuple(
        requirement.condition
        for requirement in resolution.automatic_success
        if isinstance(requirement, ConditionImmunityRequirementSchema)
    )


def automatic_success_traits(resolution: object) -> tuple[str, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    return tuple(
        requirement.trait
        for requirement in resolution.automatic_success
        if isinstance(requirement, CreatureTraitRequirementSchema)
    )
