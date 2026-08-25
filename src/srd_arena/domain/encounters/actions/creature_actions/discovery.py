"""Build actor-relative encounter action candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import (
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
)
from ...behaviors import (
    DIRECTION_DELTAS,
    is_adjacent as _is_adjacent,
    movement_budget_for,
)
from ...models import ActionCost, CreatureRef, EncounterAction
from ..attack_resolution import attack_sources
from ..consumables import healing_potions_in_inventory
from ..eligibility import action_eligibility
from ..grappling import available_escape_actions
from ..stat_block import executable_multiattack_slot_plans

if TYPE_CHECKING:
    from ...encounter import EncounterState


def available_creature_actions(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    include_attack_alternatives: bool = False,
) -> list[EncounterAction]:
    """Return candidates that pass every current eligibility rule."""

    return [
        action
        for action in creature_action_candidates(
            state,
            creature_ref,
            include_attack_alternatives=include_attack_alternatives,
        )
        if action_eligibility(state, creature_ref, action).allowed
    ]


def creature_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    include_attack_alternatives: bool = False,
) -> list[EncounterAction]:
    """Describe every generally available action before eligibility filtering."""

    enemy = state.creatures[creature_ref]
    movement_cost = state._movement_cost_for(creature_ref)
    if enemy.movement_remaining is None:
        enemy.movement_remaining = movement_budget_for(
            enemy.creature, state.definition.grid
        )
    actions: list[EncounterAction] = []
    if movement_cost is not None:
        for direction in DIRECTION_DELTAS:
            actions.append(
                EncounterAction(
                    f"Move {direction}",
                    "move",
                    direction,
                    id=f"{creature_ref}-move-{direction}",
                    creature_ref=creature_ref,
                    cost=ActionCost(movement=movement_cost),
                )
            )
    multiattack_plans = executable_multiattack_slot_plans(enemy.creature)
    for plan_index, slots in enumerate(multiattack_plans):
        plan_summary = [
            "/".join(invocation.name for invocation in slot.options)
            for slot in slots
        ]
        label = (
            "Multiattack"
            if len(multiattack_plans) == 1
            else f"Multiattack ({', '.join(plan_summary)})"
        )
        actions.append(
            EncounterAction(
                label,
                "multiattack",
                (None if len(multiattack_plans) == 1 else str(plan_index)),
                id=(
                    f"{creature_ref}-multiattack"
                    if len(multiattack_plans) == 1
                    else f"{creature_ref}-multiattack-{plan_index}"
                ),
                creature_ref=creature_ref,
                cost=ActionCost(action=1),
            )
        )
    opponent_refs = [
        target_ref
        for target_ref in state._living_creature_refs()
        if state._creatures_are_opponents(creature_ref, target_ref)
    ]
    attack_target_refs: list[str | None] = (
        list(opponent_refs) if opponent_refs else [None]
    )
    for target_ref in attack_target_refs:
        available_sources = attack_sources(enemy.creature, state.item_templates)
        if enemy.pending_multiattack:
            option_names = {
                invocation.name for invocation in enemy.pending_multiattack[0].options
            }
            available_sources = [
                source for source in available_sources if source.name in option_names
            ]
        for source in available_sources:
            for attack_type in source.attack_modes:
                source_slug = source.name.lower().replace(" ", "-")
                target_slug = (
                    target_ref.replace(":", "-")
                    if isinstance(target_ref, str)
                    else "no-target"
                )
                actions.append(
                    EncounterAction(
                        _stat_block_display_name(enemy.creature, source.name),
                        "attack",
                        target_ref,
                        id=(
                            f"{creature_ref}-attack-{source_slug}-{attack_type}-"
                            f"{target_slug}"
                        ),
                        creature_ref=creature_ref,
                        cost=ActionCost(
                            action=1 if enemy.attacks_remaining == 0 else 0
                        ),
                        source_trigger_id=(
                            source.name if enemy.pending_multiattack else None
                        ),
                        preferred_attack_type=attack_type,
                        preferred_attack_name=source.name,
                    )
                )
        actions.append(
            EncounterAction(
                "Grapple",
                "grapple",
                target_ref,
                id=(
                    f"{creature_ref}-grapple-"
                    f"{target_ref.replace(':', '-') if isinstance(target_ref, str) else 'no-target'}"
                ),
                creature_ref=creature_ref,
                cost=ActionCost(action=1 if enemy.attacks_remaining == 0 else 0),
            )
        )
    for definition in enemy.creature.stat_block_actions.values():
        if not isinstance(
            definition,
            (AutomaticActionDefinition, SavingThrowActionDefinition),
        ):
            continue
        targets: list[str | tuple[float, float] | None] = (
            [creature_ref]
            if definition.target.kind == "self"
            else [
                (
                    enemy.position.x + 1.5,
                    enemy.position.y + 0.5,
                )
            ]
            if definition.target.kind == "area"
            else [
                target_ref
                for target_ref in state._living_creature_refs()
                if state._creatures_are_opponents(creature_ref, target_ref)
            ]
            if definition.target.kind == "creature"
            else []
        )
        if definition.target.kind == "creature" and not targets:
            targets = [None]
        for target in targets:
            source_slug = definition.name.lower().replace(" ", "-")
            target_slug = (
                target.replace(":", "-")
                if isinstance(target, str)
                else "aim"
                if isinstance(target, tuple)
                else "no-target"
            )
            actions.append(
                EncounterAction(
                    _stat_block_display_name(enemy.creature, definition.name),
                    "stat_block",
                    target,
                    id=f"{creature_ref}-stat-block-{source_slug}-{target_slug}",
                    creature_ref=creature_ref,
                    preferred_attack_name=definition.name,
                    cost=ActionCost(action=1),
                )
            )
    actions.extend(state._available_feature_actions(enemy.creature))
    actions.extend(state._available_spell_actions(enemy.creature))
    for effect in state.ongoing_effects:
        end_events = effect.parameters.get("end_events", [])
        if (
            not isinstance(end_events, list)
            or [
                "adjacent_creature_wakes_target",
                "any",
            ]
            not in end_events
        ):
            continue
        for target_ref in effect.target_refs:
            wake_target_state = state.creatures.get(target_ref)
            if (
                wake_target_state is None
                or not wake_target_state.is_alive
                or target_ref == creature_ref
            ):
                continue
            if not _is_adjacent(enemy.position, wake_target_state.position):
                continue
            actions.append(
                EncounterAction(
                    f"Wake {wake_target_state.creature.name}",
                    "wake_spell_target",
                    target_ref,
                    id=f"{creature_ref}-wake-{target_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    cost=ActionCost(action=1),
                )
            )
    actions.extend(available_escape_actions(state, creature_ref))
    for item in healing_potions_in_inventory(
        enemy.creature,
        state.item_templates,
    ):
        actions.append(
            EncounterAction(
                f"Drink {item.name}",
                "utilize",
                item.id,
                id=f"{creature_ref}-utilize-drink-{item.id}",
                creature_ref=creature_ref,
                cost=ActionCost(bonus_action=1),
            )
        )
    actions.append(
        EncounterAction(
            "Wait",
            "wait",
            id=f"{creature_ref}-wait",
            creature_ref=creature_ref,
        )
    )
    return actions


def _stat_block_display_name(creature, name: str) -> str:
    return next(
        (
            declaration.display_name
            for declaration in creature.declared_stat_block_actions
            if declaration.name == name
        ),
        name,
    )
