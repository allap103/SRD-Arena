"""Saving-throw and area resolution for authored stat-block actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, cast

from srd_arena.domain.capabilities import (
    CapabilityEffect,
    ConditionEffect,
    DamageEffect,
)
from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.stat_block_actions import SavingThrowActionDefinition
from srd_arena.domain.rolls.dice import DieRoller, combine_roll_modes, resolve_dice
from srd_arena.domain.rolls.occurrences import stat_block_save_occurrence_id
from srd_arena.domain.rolls.saving_throws import (
    Ability,
    resolve_saving_throw,
)

from ...attack_economy import consume_action
from ...defeat import resolve_creature_defeat
from ...effect_lifecycle.roll_usage import resolve_saving_throw_modifier
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ...rule_queries.defenses import has_condition_save_advantage
from ...rule_queries.obstructions import cover_between
from ...rule_queries.rolls import roll_modifiers
from ...state_combat import (
    apply_combat_damage,
    automatic_save_failure_provider_ids_for,
)
from ...state_runtime import create_event
from ..d20_roll_modifiers import (
    clear_d20_roll_modes,
    consume_d20_roll_mode,
)
from .resources import consume_stat_block_action_resource
from .targets import stat_block_target_refs

if TYPE_CHECKING:
    from ...encounter import EncounterState


def resolve_saving_throw_stat_block_action(
    state: EncounterState,
    creature: Creature,
    definition: SavingThrowActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve a supported saving-throw action against all selected targets.

    >>> from types import SimpleNamespace
    >>> resolve_saving_throw_stat_block_action(
    ...     SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
    ...     EncounterAction("Breath", "stat_block"), EncounterProgress(), "breath-1"
    ... )
    Traceback (most recent call last):
    ...
    ValueError: Saving-throw stat-block action requires an aim target.
    """
    if not isinstance(action.value, (str, tuple)):
        raise ValueError("Saving-throw stat-block action requires an aim target.")
    creature_ref = state.current_decision().creature_ref
    target_refs = stat_block_target_refs(
        state,
        creature_ref,
        action.value,
        definition,
    )
    if not target_refs:
        raise ValueError("The stat-block action has no valid targets.")
    consume_action(state, allow_magic=False)
    consume_stat_block_action_resource(creature, definition.name)
    ability_names = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    outcomes: list[dict[str, object]] = []
    damage_roll_rules = roll_modifiers(
        state,
        creature_ref,
        "damage_roll",
    )
    roll_die = state.dice.roll_die
    for target_index, target_ref in enumerate(target_refs, start=1):
        target = state.creatures[target_ref].creature
        ability = cast(Ability, ability_names[definition.ability])
        roll_rules = roll_modifiers(
            state,
            target_ref,
            "saving_throw",
            ability=ability,
        )
        inflicted_conditions = tuple(
            effect.condition
            for stage in definition.failure
            for effect in stage.effects
            if isinstance(effect, ConditionEffect)
        )
        saving_throw = resolve_saving_throw(
            target,
            ability,
            definition.dc,
            mode=combine_roll_modes(
                (
                    "advantage"
                    if has_condition_save_advantage(
                        state,
                        target_ref,
                        inflicted_conditions,
                    )
                    else "normal"
                ),
                consume_d20_roll_mode(
                    state,
                    action_id,
                    stat_block_save_occurrence_id(target_index),
                ),
            ),
            sourced_modifier_override=(
                resolve_saving_throw_modifier(state, target_ref, roll_rules)
                + (
                    cover_between(state, creature_ref, target_ref).bonus
                    if ability == "dexterity"
                    else 0
                )
            ),
            sourced_mode_override=roll_rules.mode,
            roller=roll_die,
            automatic_failure_reasons=(
                automatic_save_failure_provider_ids_for(
                    state,
                    target_ref,
                    ability_names[definition.ability],
                )
            ),
        )
        effects = (
            definition.success
            if saving_throw.check.success
            else definition.failure[0].effects
        )
        damage_effects = (
            definition.failure[0].effects
            if saving_throw.check.success and definition.success_damage == "half"
            else effects
        )
        damage_resolution = apply_damage_effects(
            target,
            damage_effects,
            half=(saving_throw.check.success and definition.success_damage == "half"),
            die_roller=roll_die,
            modifier_for_roll=lambda: damage_roll_rules.resolve_modifier(roll_die),
            damage_receiver=partial(
                apply_combat_damage,
                state,
                target_ref,
            ),
        )
        non_damage_effects = (*effects, *definition.always)
        if any(not isinstance(effect, DamageEffect) for effect in non_damage_effects):
            unsupported = next(
                effect
                for effect in non_damage_effects
                if not isinstance(effect, DamageEffect)
            )
            raise NotImplementedError(
                f"Saving-throw effect '{type(unsupported).__name__}' is not executable."
            )
        always_damage_resolution = apply_damage_effects(
            target,
            definition.always,
            half=False,
            die_roller=roll_die,
            modifier_for_roll=lambda: damage_roll_rules.resolve_modifier(roll_die),
            damage_receiver=partial(
                apply_combat_damage,
                state,
                target_ref,
            ),
        )
        damage = damage_resolution.total + always_damage_resolution.total
        outcomes.append(
            {
                "target_ref": target_ref,
                "save_die": saving_throw.check.roll.selected,
                "save_dice": list(saving_throw.check.roll.dice),
                "save_selected_index": saving_throw.check.roll.selected_index,
                "save_mode": saving_throw.check.roll.mode,
                "save_modifier": saving_throw.modifiers.total,
                "save_total": saving_throw.check.roll.total,
                "save_dc": saving_throw.check.target,
                "success": saving_throw.check.success,
                "automatic_failure_reasons": list(
                    saving_throw.automatic_failure_reasons
                ),
                "damage": damage,
                "damage_details": [
                    *damage_resolution.details,
                    *always_damage_resolution.details,
                ],
            }
        )
        if target.get_health() <= 0:
            resolve_creature_defeat(
                state,
                target_ref,
                defeated_by_ref=creature_ref,
                progress=progress,
                action_id=action_id,
            )
    clear_d20_roll_modes(state, action_id)
    progress.messages.append(
        (
            "system",
            f"{creature.name} uses {definition.name}.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "stat_block_action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "action_name": definition.name,
                "outcomes": outcomes,
            },
        )
    )


@dataclass(frozen=True)
class DamageEffectsResolution:
    """Retain applied damage and individual roll details for effect groups."""

    total: int
    details: tuple[dict[str, object], ...]


def apply_damage_effects(
    target: Creature,
    effects: tuple[CapabilityEffect, ...],
    *,
    half: bool,
    die_roller: DieRoller,
    modifier_for_roll: Callable[[], int] | None = None,
    damage_receiver: Callable[[int, str | None], int] | None = None,
) -> DamageEffectsResolution:
    """Apply supported damage effects and retain each resolved dice pool.

    Successful saves can request half damage after dice and modifiers have been
    combined. The returned value reflects the target's own mitigation.

    >>> from types import SimpleNamespace
    >>> effect = DamageEffect("2d6", 2, "fire")
    >>> target = SimpleNamespace(take_damage=lambda amount: amount - 1)
    >>> resolved = apply_damage_effects(
    ...     target, (effect,), half=True,
    ...     die_roller=lambda sides: 4,
    ... )
    >>> (resolved.total, resolved.details[0]["dice_values"])
    (4, [4, 4])
    """
    total = 0
    details: list[dict[str, object]] = []
    for effect in effects:
        if not isinstance(effect, DamageEffect):
            continue
        count_text, sides_text = effect.dice.lower().split("d", 1)
        roll = resolve_dice(
            int(count_text),
            int(sides_text),
            modifier=effect.bonus,
            roller=die_roller,
        )
        sourced_modifier = modifier_for_roll() if modifier_for_roll is not None else 0
        resolved_total = roll.total + sourced_modifier
        amount = max(
            effect.minimum or 0,
            resolved_total,
        )
        if half:
            amount //= 2
        receiver = damage_receiver or (
            lambda value, _damage_type: target.take_damage(value)
        )
        applied = receiver(amount, effect.damage_type)
        total += applied
        details.append(
            {
                "dice": effect.dice,
                "dice_values": [die.result for die in roll.dice],
                "die_rolls": [list(die.rolls) for die in roll.dice],
                "dice_total": roll.subtotal,
                "modifier": roll.modifier + sourced_modifier,
                "sourced_modifier": sourced_modifier,
                "total": resolved_total,
                "halved": half,
                "minimum_applied_total": amount,
                "damage_type": effect.damage_type,
                "applied_damage": applied,
            }
        )
    return DamageEffectsResolution(total=total, details=tuple(details))
