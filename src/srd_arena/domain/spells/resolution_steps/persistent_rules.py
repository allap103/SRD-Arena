"""Select spell choices and translate persistent effects into runtime rules."""

from dataclasses import dataclass
from typing import cast

from ...capabilities import (
    ArmorClassModifierEffect,
    ConditionImmunityEffect,
    ConditionSaveAdvantageEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    EffectDuration,
    HitPointMaximumModifierEffect,
    SenseEffect,
    SpeedModifierEffect,
)
from ...effects.conditions import Condition
from ...effects.modifiers import ModifierMode, RollKind, RollModifier
from ...effects.rule_effects import (
    ArmorClassAdjustment,
    ConditionImmunity,
    ConditionSaveAdvantage,
    DamageReduction,
    DamageResistance,
    GrantedSense,
    MaximumHitPointAdjustment,
    RollAdjustment,
    RuntimeRuleEffect,
    SpeedAdjustment,
)
from .context import SpellActionContext
from .preparation import PreparedSpellResolution
from .scaling import resource_int_increment


@dataclass(frozen=True)
class PersistentRulePlan:
    """Hold translated rules and the authored duration shared by those rules."""

    effects: tuple[RuntimeRuleEffect, ...]
    duration: EffectDuration | None


def prepare_persistent_rule_plan(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
) -> PersistentRulePlan:
    """Resolve casting choices and translate persistent spell effects.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget, Outcome,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome())
    ... )
    >>> prepared = SimpleNamespace(
    ...     definition=definition, definition_effects=(), levels_above=0,
    ...     roll_modifier_effects=(),
    ... )
    >>> context = SimpleNamespace(
    ...     selected_damage_type=None, selected_ability=None
    ... )
    >>> prepare_persistent_rule_plan(context, prepared)
    PersistentRulePlan(effects=(), duration=None)
    """

    maximum_hit_point_effect = _first_effect(
        prepared,
        HitPointMaximumModifierEffect,
    )
    maximum_hit_point_modifier = (
        maximum_hit_point_effect.value if maximum_hit_point_effect is not None else 0
    ) + (
        resource_int_increment(prepared.definition, "hit_point_maximum")
        * prepared.levels_above
    )
    resistance_effect = _first_effect(prepared, DamageResistanceEffect)
    damage_resistances = (
        resistance_effect.damage_types if resistance_effect is not None else ()
    )
    if resistance_effect is not None and resistance_effect.selection == "choose_one":
        damage_resistances = (
            (context.selected_damage_type,)
            if context.selected_damage_type in resistance_effect.damage_types
            else resistance_effect.damage_types[:1]
        )
    reduction_effect = _first_effect(prepared, DamageReductionEffect)
    damage_reduction_type = (
        context.selected_damage_type
        if reduction_effect is not None
        and context.selected_damage_type in reduction_effect.damage_types
        else reduction_effect.damage_types[0]
        if reduction_effect is not None
        else None
    )
    condition_save_advantages = tuple(
        condition
        for effect in prepared.definition_effects
        if isinstance(effect, ConditionSaveAdvantageEffect)
        for condition in effect.conditions
    )
    condition_immunities = tuple(
        condition
        for effect in prepared.definition_effects
        if isinstance(effect, ConditionImmunityEffect)
        for condition in effect.conditions
    )
    senses = tuple(
        (effect.sense, effect.range_feet)
        for effect in prepared.definition_effects
        if isinstance(effect, SenseEffect)
    )
    return PersistentRulePlan(
        effects=_translate_rule_effects(
            prepared,
            context.selected_ability,
            maximum_hit_point_modifier=maximum_hit_point_modifier,
            also_modify_current=(
                maximum_hit_point_effect.also_modify_current
                if maximum_hit_point_effect is not None
                else False
            ),
            damage_resistances=damage_resistances,
            damage_reduction_type=damage_reduction_type,
            damage_reduction_dice=(
                reduction_effect.dice if reduction_effect is not None else None
            ),
            condition_immunities=condition_immunities,
            condition_save_advantages=condition_save_advantages,
            senses=senses,
        ),
        duration=next(
            (
                duration
                for effect in prepared.definition_effects
                for duration in (getattr(effect, "duration", None),)
                if isinstance(duration, EffectDuration)
            ),
            None,
        ),
    )


def _first_effect[
    EffectType: (
        HitPointMaximumModifierEffect | DamageResistanceEffect | DamageReductionEffect
    )
](
    prepared: PreparedSpellResolution,
    effect_type: type[EffectType],
) -> EffectType | None:
    """Return the first persistent effect of a requested concrete type."""

    return next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, effect_type)
        ),
        None,
    )


def _translate_rule_effects(
    prepared: PreparedSpellResolution,
    selected_ability: str | None,
    *,
    maximum_hit_point_modifier: int = 0,
    also_modify_current: bool = False,
    damage_resistances: tuple[str, ...] = (),
    damage_reduction_type: str | None = None,
    damage_reduction_dice: str | None = None,
    condition_immunities: tuple[str, ...] = (),
    condition_save_advantages: tuple[str, ...] = (),
    senses: tuple[tuple[str, int], ...] = (),
) -> tuple[RuntimeRuleEffect, ...]:
    """Translate selected persistent capability effects into runtime rules.

    >>> from types import SimpleNamespace
    >>> prepared = SimpleNamespace(
    ...     definition_effects=(
    ...         ArmorClassModifierEffect(2),
    ...         SpeedModifierEffect(10),
    ...     ),
    ...     roll_modifier_effects=(),
    ... )
    >>> _translate_rule_effects(prepared, None)
    (ArmorClassAdjustment(value=2), SpeedAdjustment(feet=10))
    """

    effects: list[RuntimeRuleEffect] = [
        ArmorClassAdjustment(effect.value)
        for effect in prepared.definition_effects
        if isinstance(effect, ArmorClassModifierEffect)
    ]
    if maximum_hit_point_modifier:
        effects.append(
            MaximumHitPointAdjustment(
                maximum_hit_point_modifier,
                also_modify_current,
            )
        )
    if damage_resistances:
        effects.append(DamageResistance(frozenset(damage_resistances)))
    if damage_reduction_type is not None and damage_reduction_dice is not None:
        effects.append(DamageReduction(damage_reduction_type, damage_reduction_dice))
    if condition_immunities:
        effects.append(
            ConditionImmunity(
                frozenset(Condition(value) for value in condition_immunities)
            )
        )
    if condition_save_advantages:
        effects.append(
            ConditionSaveAdvantage(
                frozenset(Condition(value) for value in condition_save_advantages)
            )
        )
    effects.extend(GrantedSense(sense, feet) for sense, feet in senses)
    effects.extend(
        SpeedAdjustment(effect.feet)
        for effect in prepared.definition_effects
        if isinstance(effect, SpeedModifierEffect)
    )
    for effect in prepared.roll_modifier_effects:
        abilities = effect.ability_options or (effect.ability,)
        for ability in abilities:
            if ability is not None and ability != selected_ability:
                continue
            rolls = (
                ("ability_check", "attack_roll", "saving_throw")
                if effect.roll == "d20_test"
                else (effect.roll,)
            )
            effects.extend(
                RollAdjustment(
                    RollModifier(
                        roll=cast(RollKind, roll),
                        mode=cast(ModifierMode, effect.mode),
                        dice=effect.dice,
                        value=effect.value,
                        subject=effect.subject,
                        ignored_by_senses=effect.ignored_by_senses,
                        ability=ability,
                    )
                )
                for roll in rolls
            )
    return tuple(effects)
