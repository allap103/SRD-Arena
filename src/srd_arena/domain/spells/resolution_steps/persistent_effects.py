"""Build ongoing-effect and condition results from resolved spell targets."""

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
from ...effects.results import EffectResult
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
from ...effects.runtime import (
    EndEventRule,
    OngoingEffectLifecycle,
    RepeatedDamage,
    RepeatSaveLifecycle,
)
from ..rules import spell_duration_rounds
from .context import SpellActionContext
from .details import effect_duration_rounds
from .polarity import persistent_spell_effect_polarity
from .preparation import PreparedSpellResolution
from .scaling import resource_dice_increment, resource_int_increment, scale_dice
from .targets import ResolvedSpellTargets


def build_persistent_spell_effects(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    resolved: ResolvedSpellTargets,
) -> list[EffectResult]:
    """Create ongoing effects that retain the casting source and future rules hooks.

    No runtime state is created when the spell affected no targets.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import AutomaticResolution, CapabilityDefinition
    >>> from ...capabilities import CapabilityTarget, Outcome
    >>> from ..definitions import Spell
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome())
    ... )
    >>> spell = Spell("ward", "Ward", "TEST", 1, definition=definition)
    >>> context = SimpleNamespace(
    ...     spell=spell, selected_condition=None, selected_damage_type=None,
    ...     selected_ability=None, source_ref="mage", current_round=1,
    ...     creature=SimpleNamespace(
    ...         name="Mage", spellcasting=SimpleNamespace(
    ...             save_dc=13, ability_modifier=3
    ...         )
    ...     ),
    ... )
    >>> prepared = SimpleNamespace(
    ...     definition=definition, definition_effects=(), conditions=(),
    ...     repeat_failure_damage=(), repeat_failure_conditions=(),
    ...     temporary_hit_point_effects=(), roll_modifier_effects=(),
    ...     repeat_save=None, save_ability=None, levels_above=0,
    ...     expires_on_source_turn_end=False,
    ... )
    >>> resolved = SimpleNamespace(affected_targets=())
    >>> build_persistent_spell_effects(context, prepared, resolved)
    []
    """

    spell = context.spell
    assert context.creature.spellcasting is not None

    selected_condition = context.selected_condition
    if selected_condition not in prepared.conditions:
        selected_condition = prepared.conditions[0] if prepared.conditions else None
    selected_conditions = (
        ((selected_condition,) if selected_condition is not None else ())
        if prepared.definition.condition_selection == "choose_one"
        else prepared.conditions
    )
    parent_kind = "concentration" if spell.concentration else "spell"
    duration_rounds = spell_duration_rounds(spell)
    maximum_hit_point_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, HitPointMaximumModifierEffect)
        ),
        None,
    )
    maximum_hit_point_modifier = (
        maximum_hit_point_effect.value if maximum_hit_point_effect is not None else 0
    ) + (
        resource_int_increment(prepared.definition, "hit_point_maximum")
        * prepared.levels_above
    )
    resistance_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, DamageResistanceEffect)
        ),
        None,
    )
    selected_damage_resistances = (
        resistance_effect.damage_types if resistance_effect is not None else ()
    )
    if resistance_effect is not None and resistance_effect.selection == "choose_one":
        selected_damage_resistances = (
            (context.selected_damage_type,)
            if context.selected_damage_type in resistance_effect.damage_types
            else resistance_effect.damage_types[:1]
        )
    reduction_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, DamageReductionEffect)
        ),
        None,
    )
    selected_damage_reduction_type = None
    if reduction_effect is not None:
        selected_damage_reduction_type = (
            context.selected_damage_type
            if context.selected_damage_type in reduction_effect.damage_types
            else reduction_effect.damage_types[0]
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
    rule_effects = _build_rule_effects(
        prepared,
        context.selected_ability,
        maximum_hit_point_modifier=maximum_hit_point_modifier,
        also_modify_current=(
            maximum_hit_point_effect.also_modify_current
            if maximum_hit_point_effect is not None
            else False
        ),
        damage_resistances=selected_damage_resistances,
        damage_reduction_type=selected_damage_reduction_type,
        damage_reduction_dice=(
            reduction_effect.dice if reduction_effect is not None else None
        ),
        condition_immunities=condition_immunities,
        condition_save_advantages=condition_save_advantages,
        senses=senses,
    )
    effect_duration = next(
        (
            duration
            for effect in prepared.definition_effects
            for duration in (getattr(effect, "duration", None),)
            if isinstance(duration, EffectDuration)
        ),
        None,
    )

    effects: list[EffectResult] = []
    if (
        resolved.affected_targets
        and (
            prepared.conditions
            or maximum_hit_point_modifier != 0
            or selected_damage_resistances
            or condition_save_advantages
            or rule_effects
            or selected_damage_reduction_type is not None
            or any(
                temporary.trigger == "target_turn_start"
                for temporary in prepared.temporary_hit_point_effects
            )
            or condition_immunities
            or senses
        )
        and (
            duration_rounds is not None
            or spell.concentration
            or prepared.repeat_save is not None
        )
    ):
        effects.append(
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=resolved.affected_targets[0].target_ref,
                data={
                    "effect_kind": parent_kind,
                    "source_ref": context.source_ref,
                    "polarity": persistent_spell_effect_polarity(
                        prepared,
                    ).value,
                    "source_label": context.creature.name,
                    "definition_id": spell.id,
                    "recast_ends_previous": spell.recast_ends_previous,
                    "target_refs": [
                        target.target_ref for target in resolved.affected_targets
                    ],
                    "duration_rounds": (
                        duration_rounds
                        if duration_rounds is not None
                        else effect_duration_rounds(effect_duration)
                    ),
                },
                effect_label=spell.name,
                lifecycle=OngoingEffectLifecycle(
                    started_round=context.current_round,
                    repeat_save=(
                        RepeatSaveLifecycle(
                            trigger=prepared.repeat_save.trigger,
                            ability=cast(str, prepared.repeat_save.ability),
                            dc=context.creature.spellcasting.save_dc,
                            failure_conditions=tuple(
                                Condition(value)
                                for value in prepared.repeat_failure_conditions
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
                            damage_grants_advantage=(
                                prepared.damage_repeat_save_advantage
                            ),
                        )
                        if prepared.repeat_save is not None
                        else None
                    ),
                    end_events=tuple(
                        EndEventRule(event, scope)
                        for event, scope in prepared.end_events
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
                ),
                rule_effects=rule_effects,
            )
        )

    for target in resolved.affected_targets:
        for condition in selected_conditions:
            condition_data: dict[str, object] = {
                "condition": condition,
                "source_ref": context.source_ref,
                "source_label": context.creature.name,
                "source_kind": "spell",
                "definition_id": spell.id,
            }
            if condition in spell.self_removal_blocked_conditions:
                condition_data["metadata"] = {"blocks_self_removal": True}
            if effects:
                condition_data["parent_effect_kind"] = parent_kind
            if prepared.expires_on_source_turn_end:
                condition_data["expires_on_creature_ref"] = context.source_ref
                condition_data["expires_on_round"] = context.current_round + 1
            effects.append(
                EffectResult(
                    kind="apply_condition",
                    target_ref=target.target_ref,
                    data=condition_data,
                )
            )
    return effects


def _build_rule_effects(
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
    """Translate persistent capability effects into typed runtime rules.

    >>> from types import SimpleNamespace
    >>> prepared = SimpleNamespace(
    ...     definition_effects=(
    ...         ArmorClassModifierEffect(2),
    ...         SpeedModifierEffect(10),
    ...     ),
    ...     roll_modifier_effects=(),
    ... )
    >>> _build_rule_effects(prepared, None)
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
