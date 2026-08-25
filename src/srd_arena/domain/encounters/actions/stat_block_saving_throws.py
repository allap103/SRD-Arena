"""Saving-throw and area resolution for authored stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...capabilities import CapabilityEffect, ConditionEffect, DamageEffect
from ...creatures import Creature
from ...creatures.stat_block_actions import SavingThrowActionDefinition
from ...geometry import Vector2D, build_directional_area, vector_between_positions
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .stat_block_resources import consume_stat_block_action_resource
from .stat_block_rolls import roll_dice, roll_die
from ..models import EncounterAction, EncounterProgress
from ..ongoing_effects import has_condition_save_advantage

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_saving_throw_stat_block_action(
    state: EncounterState,
    creature: Creature,
    definition: SavingThrowActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve a supported saving-throw action against all selected targets."""
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
    state._consume_action(allow_magic=False)
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
    for target_ref in target_refs:
        target = state.creatures[target_ref].creature
        inflicted_conditions = tuple(
            effect.condition
            for stage in definition.failure
            for effect in stage.effects
            if isinstance(effect, ConditionEffect)
        )
        saving_throw = resolve_saving_throw(
            cast(SavingThrowCreature, target),
            cast(Ability, ability_names[definition.ability]),
            definition.dc,
            mode=(
                "advantage"
                if has_condition_save_advantage(
                    state,
                    target_ref,
                    inflicted_conditions,
                )
                else "normal"
            ),
            roller=roll_die,
            automatic_failure_reasons=(
                state._automatic_save_failure_provider_ids_for(
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
        damage = apply_damage_effects(
            target,
            damage_effects,
            half=(saving_throw.check.success and definition.success_damage == "half"),
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
        damage += apply_damage_effects(
            target,
            definition.always,
            half=False,
        )
        outcomes.append(
            {
                "target_ref": target_ref,
                "save_total": saving_throw.check.roll.total,
                "success": saving_throw.check.success,
                "automatic_failure_reasons": list(
                    saving_throw.automatic_failure_reasons
                ),
                "damage": damage,
            }
        )
        if target.get_health() <= 0:
            state._remove_relationships_for_creature(target_ref)
    progress.messages.append(
        (
            "system",
            f"{creature.name} uses {definition.name}.",
        )
    )
    progress.events.append(
        state._event(
            "stat_block_action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "action_name": definition.name,
                "outcomes": outcomes,
            },
        )
    )


def stat_block_target_refs(
    state: EncounterState,
    creature_ref: str,
    aim: str | tuple[float, float],
    definition: SavingThrowActionDefinition,
) -> tuple[str, ...]:
    """Resolve creature references covered by a stat-block action target."""
    target = definition.target
    if target.kind == "self":
        return (creature_ref,)
    if target.kind == "creature":
        if not isinstance(aim, str):
            raise ValueError("A creature-targeted action requires a creature target.")
        return (aim,)
    if target.origin != "self":
        raise NotImplementedError("Point-origin stat-block areas are not executable.")
    actor_position = state.creatures[creature_ref].position
    direction = (
        vector_between_positions(actor_position, state.creatures[aim].position)
        if isinstance(aim, str)
        else Vector2D(
            aim[0] - (actor_position.x + 0.5),
            aim[1] - (actor_position.y + 0.5),
        )
    )
    grid = state.definition.grid
    size_squares = int(
        grid.distance_from_feet(target.size_feet or grid.square_size_feet, minimum=1)
    )
    width_squares = max(
        1.0,
        (target.width_feet or grid.square_size_feet) / grid.square_size_feet,
    )
    area = build_directional_area(
        target.shape,
        actor_position,
        direction,
        size_squares,
        state.definition.grid,
        width_squares=width_squares,
        coverage_threshold=(
            state.geometry_config.directional_area_cell_coverage_threshold
        ),
    )
    if area is None:
        raise NotImplementedError(f"Area shape '{target.shape}' is not executable.")
    occupied = {(cell.x, cell.y) for cell in area.cells}
    return tuple(
        target_ref
        for target_ref, target_state in state.creatures.items()
        if target_state.is_alive
        and (target_state.position.x, target_state.position.y) in occupied
    )


def apply_damage_effects(
    target: Creature,
    effects: tuple[CapabilityEffect, ...],
    *,
    half: bool,
) -> int:
    """Apply supported damage effects and return damage actually received."""
    total = 0
    for effect in effects:
        if not isinstance(effect, DamageEffect):
            continue
        count_text, sides_text = effect.dice.lower().split("d", 1)
        amount = max(
            effect.minimum or 0,
            roll_dice(int(count_text), int(sides_text)) + effect.bonus,
        )
        if half:
            amount //= 2
        total += target.take_damage(amount, effect.damage_type)
    return total
