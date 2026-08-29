"""Apply healing and temporary Hit Points to one affected spell target."""

from dataclasses import dataclass

from .context import SpellActionContext, SpellTargetContext
from .details import restoration_detail, roll_optional_dice
from .preparation import PreparedSpellResolution
from .scaling import resource_int_increment


@dataclass
class TargetRestorationResult:
    """Collect healing and temporary-Hit-Point details for one target."""

    healing_details: list[dict[str, object]]
    temporary_hit_point_details: list[dict[str, object]]


def restore_target(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
) -> TargetRestorationResult:
    """Apply prepared healing and temporary Hit Points to an affected target.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget,
    ...     HealingEffect, Outcome,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome())
    ... )
    >>> context = SimpleNamespace(
    ...     creature=SimpleNamespace(
    ...         spellcasting=SimpleNamespace(ability_modifier=3)
    ...     ),
    ...     environment=SimpleNamespace(
    ...         roll_die=lambda sides: 4,
    ...         apply_healing=lambda target_ref, amount: amount,
    ...         grant_temporary_hit_points=lambda target_ref, amount: amount,
    ...     ),
    ...     healing_allocations={"hero": 6},
    ... )
    >>> prepared = SimpleNamespace(
    ...     shared_healing_rolls=(), healing_effects=(HealingEffect(pool=10),),
    ...     temporary_hit_point_effects=(), definition=definition, levels_above=0,
    ... )
    >>> target = SimpleNamespace(
    ...     target_ref="hero", target_label="Hero",
    ... )
    >>> result = restore_target(context, prepared, target)
    >>> result.healing_details[0]["allocated"]
    6
    """

    assert context.creature.spellcasting is not None

    healing_details: list[dict[str, object]] = []
    temporary_hit_point_details: list[dict[str, object]] = []
    for healing, dice, healing_roll in prepared.shared_healing_rolls:
        modifier = healing.bonus + (
            context.creature.spellcasting.ability_modifier
            if healing.modifier == "ability_modifier"
            else 0
        )
        modifier += (
            resource_int_increment(prepared.definition, "healing_bonus")
            * prepared.levels_above
        )
        total = (
            target.creature.get_max_health() - target.creature.get_health()
            if healing.restore_to_maximum
            else max(
                0,
                (healing_roll.subtotal if healing_roll is not None else 0) + modifier,
            )
        )
        applied = context.environment.apply_healing(target.target_ref, total)
        healing_details.append(
            restoration_detail(
                target,
                dice=dice,
                roll=healing_roll,
                modifier=modifier,
                total=total,
                applied=applied,
            )
        )
    for healing in prepared.healing_effects:
        if healing.pool is None:
            continue
        allocated = context.healing_allocations.get(target.target_ref, 0)
        applied = context.environment.apply_healing(target.target_ref, allocated)
        detail = restoration_detail(
            target,
            dice=None,
            roll=None,
            modifier=0,
            total=allocated,
            applied=applied,
        )
        detail["allocated"] = allocated
        healing_details.append(detail)
    for temporary in prepared.temporary_hit_point_effects:
        if temporary.trigger != "application":
            continue
        temporary_roll = roll_optional_dice(
            temporary.dice,
            context.environment.roll_die,
        )
        modifier = temporary.value + (
            context.creature.spellcasting.ability_modifier
            if temporary.modifier == "ability_modifier"
            else 0
        )
        modifier += (
            resource_int_increment(
                prepared.definition,
                "temporary_hit_points",
            )
            * prepared.levels_above
        )
        total = max(
            0,
            (temporary_roll.subtotal if temporary_roll is not None else 0) + modifier,
        )
        granted = context.environment.grant_temporary_hit_points(
            target.target_ref,
            total,
        )
        temporary_hit_point_details.append(
            restoration_detail(
                target,
                dice=temporary.dice,
                roll=temporary_roll,
                modifier=modifier,
                total=total,
                applied=granted,
            )
        )
    return TargetRestorationResult(
        healing_details=healing_details,
        temporary_hit_point_details=temporary_hit_point_details,
    )
