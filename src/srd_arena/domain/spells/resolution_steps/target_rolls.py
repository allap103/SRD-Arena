"""Resolve the save or attack roll for one spell target."""

from dataclasses import dataclass
from typing import cast

from srd_arena.domain.capabilities import AttackResolution, SavingThrowResolution
from srd_arena.domain.rolls.dice import (
    DicePoolResult,
    combine_roll_modes,
    resolve_check,
    resolve_d20,
    resolve_dice,
)
from srd_arena.domain.rolls.saving_throws import (
    Ability,
    resolve_saving_throw,
)

from ..definitions import SpellDamage
from .context import SpellActionContext, SpellTargetContext
from .preparation import PreparedSpellResolution
from .scaling import parse_damage_dice


@dataclass
class TargetRollOutcome:
    """Collect one target's save/attack result and resulting damage rolls."""

    successful_save: bool
    automatic_success_reasons: tuple[str, ...]
    hit: bool
    damage_rolls: list[tuple[SpellDamage, DicePoolResult]]
    save_detail: dict[str, object] | None = None
    attack_detail: dict[str, object] | None = None


def resolve_target_roll(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
    *,
    projectile_index: int,
) -> TargetRollOutcome:
    """Resolve the attack roll or saving throw required for one spell target.

    Automatic resolutions affect their target without making a d20 roll.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.capabilities import AutomaticResolution, Outcome
    >>> context = SimpleNamespace(
    ...     creature=SimpleNamespace(spellcasting=object()),
    ...     roller=lambda sides: 10,
    ... )
    >>> prepared = SimpleNamespace(
    ...     resolution=AutomaticResolution(Outcome()), shared_damage_rolls=()
    ... )
    >>> outcome = resolve_target_roll(
    ...     context, prepared, SimpleNamespace(), projectile_index=1
    ... )
    >>> (outcome.hit, outcome.save_detail, outcome.attack_detail)
    (True, None, None)
    """

    assert context.creature.spellcasting is not None
    if isinstance(prepared.resolution, SavingThrowResolution):
        return _resolve_saving_throw(context, prepared, target)
    if isinstance(prepared.resolution, AttackResolution):
        return _resolve_spell_attack(
            context,
            prepared,
            target,
            projectile_index=projectile_index,
        )
    return TargetRollOutcome(
        successful_save=False,
        automatic_success_reasons=(),
        hit=True,
        damage_rolls=list(prepared.shared_damage_rolls),
    )


def _resolve_saving_throw(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
) -> TargetRollOutcome:
    """Resolve one target's spell saving throw and its structured detail."""

    assert context.creature.spellcasting is not None
    ability = prepared.save_ability or "dexterity"
    creature_type = (target.creature.statistics.creature_type or "").casefold()
    automatic_failure_reasons = target.automatic_failure_reasons(ability)
    if creature_type in prepared.automatic_failure_creature_types:
        automatic_failure_reasons += (f"{context.spell.name}: {creature_type}",)
    automatic_success_reasons = _automatic_success_reasons(
        context,
        prepared,
        target,
    )
    if automatic_success_reasons:
        return TargetRollOutcome(
            successful_save=True,
            automatic_success_reasons=automatic_success_reasons,
            hit=True,
            damage_rolls=list(prepared.shared_damage_rolls),
            save_detail={
                "target_ref": target.target_ref,
                "target_label": target.target_label,
                "ability": ability,
                "target_dc": context.creature.spellcasting.save_dc,
                "success": True,
                "automatic_success_reasons": list(automatic_success_reasons),
                "automatic_failure_reasons": [],
            },
        )

    base_mode = context.save_roll_modes.get(
        target.target_ref,
        (
            "disadvantage"
            if creature_type in prepared.disadvantage_creature_types
            else "normal"
        ),
    )
    save = resolve_saving_throw(
        target.creature,
        cast(Ability, ability),
        context.creature.spellcasting.save_dc,
        mode=base_mode,
        sourced_modifier_override=context.environment.saving_throw_modifier(
            target.target_ref,
            ability,
        ),
        sourced_mode_override=context.environment.saving_throw_mode(
            target.target_ref,
            ability,
        ),
        roller=context.environment.roll_die,
        automatic_failure_reasons=automatic_failure_reasons,
    )
    return TargetRollOutcome(
        successful_save=save.check.success,
        automatic_success_reasons=(),
        hit=True,
        damage_rolls=list(prepared.shared_damage_rolls),
        save_detail={
            "target_ref": target.target_ref,
            "target_label": target.target_label,
            "ability": ability,
            "die": save.check.roll.selected,
            "modifier": save.modifiers.total,
            "total": save.check.roll.total,
            "target_dc": save.check.target,
            "success": save.check.success,
            "automatic_success_reasons": [],
            "automatic_failure_reasons": list(save.automatic_failure_reasons),
        },
    )


def _automatic_success_reasons(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
) -> tuple[str, ...]:
    """Explain target facts that make the spell save succeed automatically."""

    immunity_reasons = tuple(
        f"{context.spell.name}: immune to {condition}"
        for condition in prepared.automatic_success_condition_immunities
        if condition in target.condition_immunities
    )
    trait_reasons = tuple(
        f"{context.spell.name}: {trait}"
        for trait in prepared.automatic_success_traits
        if trait in target.creature.statistics.mechanical_traits
    )
    return immunity_reasons + trait_reasons


def _resolve_spell_attack(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
    *,
    projectile_index: int,
) -> TargetRollOutcome:
    """Resolve one target's spell attack and any per-projectile damage dice."""

    assert context.creature.spellcasting is not None
    attack = resolve_d20(
        modifier=(
            context.creature.spellcasting.attack_bonus
            + context.environment.attack_roll_modifier(target.target_ref)
        ),
        mode=combine_roll_modes(
            context.attack_roll_modes.get(target.target_ref, "normal"),
            context.environment.attack_roll_mode(target.target_ref),
        ),
        roller=context.environment.roll_die,
    )
    target_ac = context.target_armor_classes.get(
        target.target_ref,
        target.creature.get_armor_class(),
    )
    check = resolve_check(attack, target_ac)
    hit = attack.selected != 1 and (attack.selected == 20 or check.success)
    automatic_critical = context.automatic_critical_providers.get(
        target.target_ref,
        (),
    )
    critical_hit = hit and (attack.selected == 20 or bool(automatic_critical))
    damage_rolls = list(prepared.shared_damage_rolls)
    for damage in prepared.damage_definitions:
        count, sides = parse_damage_dice(damage.dice)
        if critical_hit:
            count *= 2
        damage_rolls.append(
            (
                damage,
                resolve_dice(
                    count,
                    sides,
                    modifier=context.environment.damage_roll_modifier(),
                    roller=context.environment.roll_die,
                ),
            )
        )
    return TargetRollOutcome(
        successful_save=False,
        automatic_success_reasons=(),
        hit=hit,
        damage_rolls=damage_rolls,
        attack_detail={
            "projectile_index": projectile_index,
            "target_ref": target.target_ref,
            "target_label": target.target_label,
            "die": attack.selected,
            "modifier": attack.total - attack.selected,
            "total": attack.total,
            "target_ac": target_ac,
            "hit": hit,
            "critical_hit": critical_hit,
            "automatic_critical_provider_ids": list(automatic_critical),
        },
    )
