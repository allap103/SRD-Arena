from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...creatures import Creature, MultiattackStep
from ...creatures.stat_block_actions import (
    ActionEffect,
    AutomaticActionDefinition,
    AttackActionDefinition,
    ConditionEffect,
    DamageEffect,
    SavingThrowActionDefinition,
)
from ...geometry import (
    Vector2D,
    build_directional_area,
    vector_between_positions,
)
from ...effects.conditions import Condition
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .attack_resolution import (
    apply_attack_damage,
    resolve_attack,
    selected_attack_type,
)
from .hit_effects import apply_attack_hit_effects
from ..ongoing_effects import resolve_concentration_damage
from ..models import EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def executable_multiattack_sequence(creature: Creature):
    plans = executable_multiattack_slot_plans(creature)
    if not plans or any(len(slot.options) != 1 for slot in plans[0]):
        return None
    return tuple(slot.options[0] for slot in plans[0])


def executable_multiattack_slot_plans(
    creature: Creature,
) -> tuple[tuple[MultiattackStep, ...], ...]:
    if creature.multiattack is None:
        return ()
    return creature.multiattack.executable_slot_plans(
        {
            action.name
            for action in creature.stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )


def stat_block_action_resource_available(
    creature: Creature,
    action_name: str,
) -> bool:
    definition = creature.stat_block_actions.get(action_name)
    resource = getattr(definition, "resource", None)
    if resource is None:
        resource = getattr(definition, "shared_resource", None)
    if resource is None:
        return True
    return creature.stat_block_action_resources.get(action_name, 0) > 0


def stat_block_action_runtime_issue(
    definition: object,
) -> str | None:
    if isinstance(definition, AttackActionDefinition):
        for effect in definition.hit:
            if isinstance(effect, DamageEffect):
                continue
            if isinstance(effect, ConditionEffect):
                try:
                    Condition(effect.condition)
                except ValueError:
                    return (
                        f"Condition '{effect.condition}' is not supported by "
                        "the condition runtime yet."
                    )
                if effect.condition != "grappled" and effect.requirements:
                    return (
                        "Conditional attack-applied conditions are not "
                        "executable yet."
                    )
                if effect.condition != "grappled" and effect.ends_on:
                    return (
                        "Event-ended attack-applied conditions are not "
                        "executable yet."
                    )
                if effect.duration is not None and effect.duration.kind not in {
                    "start_of_turn",
                    "end_of_turn",
                }:
                    return (
                        f"Condition duration '{effect.duration.kind}' is not "
                        "executable for attack actions yet."
                    )
                continue
            return (
                f"{type(effect).__name__} is not executable for attack "
                "actions yet."
            )
        return None
    elif isinstance(definition, AutomaticActionDefinition):
        effects = definition.effects
    elif isinstance(definition, SavingThrowActionDefinition):
        if len(definition.failure) != 1:
            return "Staged saving-throw failures are not executable yet."
        if definition.failure[0].repeat_saves:
            return "Repeated saving throws are not executable yet."
        if definition.target.kind == "area" and definition.target.origin != "self":
            return "Point-origin stat-block areas are not executable yet."
        effects = (
            *definition.failure[0].effects,
            *definition.success,
            *definition.always,
        )
    else:
        return "This stat-block action type is not executable yet."
    unsupported = next(
        (effect for effect in effects if not isinstance(effect, DamageEffect)),
        None,
    )
    if unsupported is not None:
        return (
            f"{type(unsupported).__name__} is not executable for "
            "stat-block actions yet."
        )
    return None


def consume_stat_block_action_resource(
    creature: Creature,
    action_name: str,
) -> None:
    if not stat_block_action_resource_available(creature, action_name):
        raise RuntimeError(f"'{action_name}' has no uses remaining.")
    if action_name in creature.stat_block_action_resources:
        creature.stat_block_action_resources[action_name] -= 1


def recharge_stat_block_actions(creature: Creature) -> None:
    for name, definition in creature.stat_block_actions.items():
        resource = getattr(definition, "resource", None)
        if resource is None or resource.kind != "recharge":
            continue
        if creature.stat_block_action_resources.get(name, 1) > 0:
            continue
        minimum = resource.minimum or 6
        if _roll_die(6) >= minimum:
            creature.stat_block_action_resources[name] = 1


def resolve_multiattack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0 or creature_state.attacks_remaining > 0:
        raise RuntimeError("No Action remains to make a Multiattack.")
    plans = executable_multiattack_slot_plans(creature)
    selected_plan = (
        int(action.value)
        if isinstance(action.value, str) and action.value.isdigit()
        else 0
    )
    if selected_plan >= len(plans):
        raise RuntimeError("This creature has no executable Multiattack plan.")
    slots = plans[selected_plan]
    state._consume_action(allow_magic=False)
    creature_state.pending_multiattack = list(slots)
    creature_state.attacks_remaining = len(slots)
    progress.messages.append(("system", f"{creature.name} begins Multiattack."))
    progress.events.append(
        state._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "multiattack",
                "slots": [
                    [invocation.name for invocation in slot.options] for slot in slots
                ],
            },
        )
    )


def resolve_attack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    preferred_attack_name = action.preferred_attack_name
    if creature_state.pending_multiattack:
        slot = creature_state.pending_multiattack[0]
        if preferred_attack_name not in {
            invocation.name for invocation in slot.options
        }:
            raise ValueError(
                "The selected attack is not available for this Multiattack slot."
            )
        creature_state.pending_multiattack.pop(0)
        creature_state.attacks_remaining = len(creature_state.pending_multiattack)
    elif creature_state.attacks_remaining == 0:
        if creature_state.actions_remaining <= 0:
            raise RuntimeError("No Action remains to make an attack.")
        state._consume_action(allow_magic=False)
        creature_state.attacks_remaining = max(
            0,
            creature.combat_profile.attacks_per_attack_action - 1,
        )
    else:
        creature_state.attacks_remaining -= 1
    if not isinstance(action.value, str):
        raise ValueError("Attack action requires a creature reference.")
    target_ref = action.value
    if not state._creatures_are_opponents(creature_ref, target_ref):
        raise ValueError("Attack target must belong to an opposing team.")
    defender = state.creatures[target_ref].creature
    target_label = state._creature_label(target_ref)
    nearby_opponent_positions = tuple(
        candidate.position
        for opponent_ref, candidate in state.creatures.items()
        if candidate.is_alive
        and state._creatures_are_opponents(creature_ref, opponent_ref)
    )
    outcome = resolve_attack(
        creature,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
        items_by_id=state.item_templates,
        attacker_position=creature_state.position,
        nearby_opponent_positions=nearby_opponent_positions,
        preferred_attack_name=preferred_attack_name,
        preferred_attack_type=action.preferred_attack_type,
        attack_roll_mode_override=state._attack_roll_mode_for(
            creature_ref,
            target_ref,
            selected_attack_type(
                creature,
                state.item_templates,
                preferred_attack_type=action.preferred_attack_type,
            ),
            creature_state.position,
            nearby_opponent_positions,
        ),
        d20_roller=_roll_die,
        dice_roller=_roll_dice,
        automatic_critical_provider_ids=(
            state._automatic_critical_provider_ids_for(
                creature_ref,
                target_ref,
            )
        ),
    )
    if isinstance(preferred_attack_name, str):
        consume_stat_block_action_resource(creature, preferred_attack_name)
    apply_attack_damage(
        outcome,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
    )
    resolve_concentration_damage(state, target_ref, outcome.damage, progress)
    if outcome.hit and defender.get_health() > 0:
        apply_attack_hit_effects(
            state,
            attacker_ref=creature_ref,
            target_ref=target_ref,
            effects=outcome.hit_effects,
            progress=progress,
            origin_id=action_id,
        )
    progress.messages.extend(outcome.messages)
    progress.events.append(
        state._event(
            "attack_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "attacker_label": creature.name,
                "target_ref": target_ref,
                "target_label": target_label,
                "attack_name": preferred_attack_name,
                "attack_roll": outcome.attack_roll,
                "attack_roll_detail": outcome.attack_roll_detail,
                "hit": outcome.hit,
                "critical_hit": outcome.critical_hit,
                "damage": outcome.damage,
                "damage_roll_detail": outcome.damage_roll_detail,
                "attacks_remaining": creature_state.attacks_remaining,
            },
        )
    )
    if defender.get_health() <= 0:
        state._remove_relationships_for_creature(target_ref)
        progress.events.append(
            state._event(
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )


def resolve_stat_block_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    definition = creature.stat_block_actions.get(action.preferred_attack_name or "")
    if isinstance(definition, AutomaticActionDefinition):
        _resolve_automatic_action(
            state,
            creature,
            definition,
            action,
            progress,
            action_id,
        )
        return
    if isinstance(definition, SavingThrowActionDefinition):
        _resolve_saving_throw_action(
            state,
            creature,
            definition,
            action,
            progress,
            action_id,
        )
        return
    raise ValueError("Executable stat-block action definition required.")


def _resolve_automatic_action(
    state: EncounterState,
    creature: Creature,
    definition: AutomaticActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = state.current_decision().creature_ref
    if not isinstance(action.value, str):
        raise ValueError("Automatic stat-block action requires a target.")
    target_ref = action.value
    target = state.creatures[target_ref].creature
    state._consume_action(allow_magic=False)
    consume_stat_block_action_resource(creature, definition.name)
    damage = 0
    damage_details: list[dict[str, object]] = []
    for effect in definition.effects:
        if not isinstance(effect, DamageEffect):
            raise NotImplementedError(
                f"Automatic effect '{type(effect).__name__}' is not executable."
            )
        count_text, sides_text = effect.dice.lower().split("d", 1)
        rolled = _roll_dice(int(count_text), int(sides_text))
        amount = max(effect.minimum or 0, rolled + effect.bonus)
        applied = target.take_damage(amount)
        damage += applied
        damage_details.append(
            {
                "damage_type": effect.damage_type,
                "rolled": rolled,
                "bonus": effect.bonus,
                "applied": applied,
            }
        )
    progress.messages.append(
        (
            "system",
            f"{creature.name} uses {definition.name} on {target.name}, "
            f"dealing {damage} damage.",
        )
    )
    progress.events.append(
        state._event(
            "stat_block_action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "action_name": definition.name,
                "target_ref": target_ref,
                "damage": damage,
                "damage_details": damage_details,
            },
        )
    )
    if target.get_health() <= 0:
        state._remove_relationships_for_creature(target_ref)
        progress.events.append(
            state._event(
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )


def _resolve_saving_throw_action(
    state: EncounterState,
    creature: Creature,
    definition: SavingThrowActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    if not isinstance(action.value, (str, tuple)):
        raise ValueError("Saving-throw stat-block action requires an aim target.")
    creature_ref = state.current_decision().creature_ref
    target_refs = _stat_block_target_refs(
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
        saving_throw = resolve_saving_throw(
            cast(SavingThrowCreature, target),
            cast(Ability, ability_names[definition.ability]),
            definition.dc,
            roller=_roll_die,
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
        damage = _apply_damage_effects(
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
        damage += _apply_damage_effects(
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


def _stat_block_target_refs(
    state: EncounterState,
    creature_ref: str,
    aim: str | tuple[float, float],
    definition: SavingThrowActionDefinition,
) -> tuple[str, ...]:
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
    feet_per_square = state.creatures[
        creature_ref
    ].creature.attributes.movement.feet_per_square
    size_squares = max(1, (target.size_feet or 5) // feet_per_square)
    width_squares = max(
        1.0,
        (target.width_feet or feet_per_square) / feet_per_square,
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


def _apply_damage_effects(
    target: Creature,
    effects: tuple[ActionEffect, ...],
    *,
    half: bool,
) -> int:
    total = 0
    for effect in effects:
        if not isinstance(effect, DamageEffect):
            continue
        count_text, sides_text = effect.dice.lower().split("d", 1)
        amount = max(
            effect.minimum or 0,
            _roll_dice(int(count_text), int(sides_text)) + effect.bonus,
        )
        if half:
            amount //= 2
        total += target.take_damage(amount)
    return total
