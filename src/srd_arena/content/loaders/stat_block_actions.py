import re

from srd_arena.content.schemas import action_mechanics as schema
from srd_arena.content.schemas.bestiary import (
    BestiaryActionSchema,
    BestiaryMonsterSchema,
)
from srd_arena.domain.creatures import stat_block_actions as domain


def build_stat_block_actions(
    stat_block: BestiaryMonsterSchema | None,
) -> dict[str, domain.StatBlockActionDefinition]:
    if stat_block is None:
        return {}
    definitions: dict[str, domain.StatBlockActionDefinition] = {}
    for action in stat_block.action:
        mechanics = action.mechanics
        if isinstance(mechanics, schema.AttackActionMechanicsSchema):
            definitions[action.name] = _attack_definition(action, mechanics)
        elif isinstance(mechanics, schema.SavingThrowActionMechanicsSchema):
            definitions[action.name] = domain.SavingThrowActionDefinition(
                name=action.name,
                target=_target(mechanics.target),
                ability=mechanics.ability,
                dc=mechanics.dc,
                failure=tuple(
                    domain.ActionOutcomeStage(
                        effects=tuple(_effect(effect) for effect in stage.effects),
                        repeat_saves=tuple(
                            _repeat_save(repeat)
                            for repeat in stage.repeat_saves
                        ),
                    )
                    for stage in mechanics.failure
                ),
                success=tuple(_effect(effect) for effect in mechanics.success),
                success_damage=mechanics.success_damage,
                always=tuple(_effect(effect) for effect in mechanics.always),
                resource=_resource(mechanics.resource),
            )
        else:
            fallback = _parse_tagged_attack(action)
            if fallback is not None:
                definitions[action.name] = fallback
    return definitions


def _attack_definition(
    action: BestiaryActionSchema,
    mechanics: schema.AttackActionMechanicsSchema,
) -> domain.AttackActionDefinition:
    return domain.AttackActionDefinition(
        name=action.name,
        attack_modes=tuple(mechanics.attack_modes),
        attack_bonus=mechanics.attack_bonus,
        target=_target(mechanics.target),
        reach_feet=mechanics.reach_feet,
        range_normal_feet=mechanics.range_normal_feet,
        range_long_feet=mechanics.range_long_feet,
        hit=tuple(_effect(effect) for effect in mechanics.hit),
    )


def _parse_tagged_attack(
    action: BestiaryActionSchema,
) -> domain.AttackActionDefinition | None:
    if not action.entries or not isinstance(action.entries[0], str):
        return None
    entry = action.entries[0]
    attack_tag = re.search(r"\{@atk(?:r)?\s+([^}]+)\}", entry)
    hit = re.search(r"\{@hit\s+([+-]?\d+)\}", entry)
    damage = re.search(
        r"\{@damage\s+(\d+d\d+)(?:\s*\+\s*(\d+))?\}",
        entry,
    )
    damage_type = re.search(
        r"\{@damage[^}]+\}\)?\s*([A-Za-z]+)\s+damage",
        entry,
    )
    if attack_tag is None or hit is None or damage is None or damage_type is None:
        return None
    attack_modes = _parse_attack_modes(attack_tag.group(1))
    if not attack_modes:
        return None
    reach = re.search(r"reach\s+(\d+)\s*ft", entry)
    attack_range = re.search(r"range\s+(\d+)\/(\d+)\s*ft", entry)
    return domain.AttackActionDefinition(
        name=action.name,
        attack_modes=attack_modes,
        attack_bonus=int(hit.group(1)),
        target=domain.ActionTarget(kind="creature"),
        reach_feet=int(reach.group(1)) if reach is not None else None,
        range_normal_feet=(
            int(attack_range.group(1)) if attack_range is not None else None
        ),
        range_long_feet=(
            int(attack_range.group(2)) if attack_range is not None else None
        ),
        hit=(
            domain.DamageEffect(
                dice=damage.group(1),
                bonus=int(damage.group(2) or 0),
                damage_type=damage_type.group(1).lower(),
            ),
        ),
    )


def _parse_attack_modes(value: str) -> tuple[str, ...]:
    modes: list[str] = []
    for token in value.split(","):
        token = token.strip()
        if "m" in token and "melee" not in modes:
            modes.append("melee")
        if "r" in token and "ranged" not in modes:
            modes.append("ranged")
    return tuple(modes)


def _target(value: schema.ActionTargetSchema) -> domain.ActionTarget:
    return domain.ActionTarget(
        kind=value.type,
        range_feet=getattr(value, "range_feet", None),
        shape=getattr(value, "shape", None),
        size_feet=getattr(value, "size_feet", None),
        width_feet=getattr(value, "width_feet", None),
        line_of_sight=getattr(value, "line_of_sight", False),
        requirements=tuple(
            _requirement(requirement)
            for requirement in getattr(value, "requirements", ())
        ),
    )


def _requirement(value) -> domain.ActionRequirement:
    if isinstance(value, schema.SizeRequirementSchema):
        return domain.SizeRequirement(value.maximum, value.minimum)
    if isinstance(value, schema.ConditionRequirementSchema):
        return domain.ConditionRequirement(
            tuple(value.conditions),
            value.match,
            value.applied_by,
        )
    if isinstance(value, schema.CreatureTypeRequirementSchema):
        return domain.CreatureTypeRequirement(tuple(value.creature_types))
    return domain.NotAffectedRequirement(value.action)


def _duration(value) -> domain.EffectDuration | None:
    if value is None:
        return None
    return domain.EffectDuration(
        kind=value.type,
        amount=getattr(value, "amount", None),
        unit=getattr(value, "unit", None),
        creature=getattr(value, "creature", None),
        turn_offset=getattr(value, "turn_offset", 0),
        events=tuple(getattr(value, "events", ())),
    )


def _effect(value: schema.ActionEffectSchema) -> domain.ActionEffect:
    if isinstance(value, schema.DamageEffectSchema):
        return domain.DamageEffect(
            value.dice,
            value.bonus,
            value.damage_type,
            value.minimum,
            tuple(
                domain.AttackRollModeRequirement(requirement.mode)
                for requirement in value.requirements
            ),
        )
    if isinstance(value, schema.ConditionEffectSchema):
        return domain.ConditionEffect(
            condition=value.condition,
            duration=_duration(value.duration),
            requirements=tuple(
                _requirement(requirement)
                for requirement in value.requirements
            ),
            escape_dc=value.escape_dc,
            source_capacity=value.source_capacity,
            ends_on=tuple(value.ends_on),
        )
    if isinstance(value, schema.ForcedMovementEffectSchema):
        return domain.ForcedMovementEffect(
            value.direction,
            value.distance_feet,
            value.up_to,
        )
    if isinstance(value, schema.SpeedMultiplierEffectSchema):
        return domain.SpeedMultiplierEffect(
            value.numerator,
            value.denominator,
            _duration(value.duration),
        )
    if isinstance(value, schema.ProhibitReactionEffectSchema):
        return domain.ProhibitReactionsEffect(_duration(value.duration))
    if isinstance(value, schema.TurnEconomyRestrictionEffectSchema):
        return domain.TurnEconomyRestrictionEffect(
            tuple(value.choose_between),
            _duration(value.duration),
        )
    if isinstance(value, schema.RollModifierEffectSchema):
        return domain.RollModifierEffect(
            value.roll,
            value.mode,
            value.ability,
            value.dice,
            value.value,
            _duration(value.duration),
        )
    if isinstance(value, schema.ControlEffectSchema):
        return domain.ControlEffect(
            value.communication,
            value.communication_range_feet,
            value.control_range_feet,
            _duration(value.duration),
        )
    return domain.GainMemoriesEffect(
        domain.CreatureTypeRequirement(
            tuple(value.requirement.creature_types)
        ),
        value.trigger,
    )


def _repeat_save(value: schema.RepeatSaveSchema) -> domain.RepeatSave:
    return domain.RepeatSave(
        trigger=value.trigger,
        interval_amount=value.interval_amount,
        interval_unit=value.interval_unit,
        distance_from_source_feet=value.distance_from_source_feet,
        effects_end_on_success=value.effects_end_on_success,
        automatic_success_after=_duration(value.automatic_success_after),
    )


def _resource(value) -> domain.ActionResource | None:
    if value is None:
        return None
    return domain.ActionResource(
        kind=value.type,
        maximum=getattr(value, "maximum", None),
        reset=getattr(value, "reset", None),
        die=getattr(value, "die", None),
        minimum=getattr(value, "minimum", None),
    )
