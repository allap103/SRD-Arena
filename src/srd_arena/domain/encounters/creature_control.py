from __future__ import annotations

from typing import TYPE_CHECKING

from ..geometry import Position
from ..creatures import AutomaticActionDefinition
from .actions.attack_resolution import attack_sources
from .actions.consumables import healing_potions_in_inventory
from .actions.eligibility import action_eligibility, require_action_eligible
from .actions.grappling import available_escape_actions, resolve_escape_action
from .actions.stat_block import (
    executable_multiattack_sequence,
    resolve_attack_action,
    resolve_multiattack_action,
)
from .behaviors import (
    DIRECTION_DELTAS,
    movement_squares as _movement_squares,
)
from .models import (
    ActionCost,
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
    CreatureRef,
    DecisionFrame,
    EncounterAction,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def _lower_initial(label: str) -> str:
    return label[:1].lower() + label[1:]


def available_creature_actions(
    self: EncounterState,
    creature_ref: CreatureRef,
    *,
    include_attack_alternatives: bool = False,
) -> list[EncounterAction]:
    enemy = self.creatures[creature_ref]
    movement_cost = self._movement_cost_for(creature_ref)
    if enemy.movement_remaining is None:
        enemy.movement_remaining = _movement_squares(enemy.creature)
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
    multiattack_sequence = executable_multiattack_sequence(enemy.creature)
    if multiattack_sequence is not None:
        actions.append(
            EncounterAction(
                "Multiattack",
                "multiattack",
                id=f"{creature_ref}-multiattack",
                creature_ref=creature_ref,
                cost=ActionCost(action=1),
            )
        )
    for target_ref in self._living_creature_refs():
        if target_ref == creature_ref:
            continue
        available_sources = (
            attack_sources(enemy.creature, self.item_templates)
            if (
                multiattack_sequence is None
                or enemy.pending_multiattack
                or include_attack_alternatives
            )
            else []
        )
        if enemy.pending_multiattack:
            available_sources = [
                source
                for source in available_sources
                if source.name == enemy.pending_multiattack[0].name
            ]
        for source in available_sources:
            for attack_type in source.attack_modes:
                source_slug = source.name.lower().replace(" ", "-")
                actions.append(
                    EncounterAction(
                        (
                            f"{source.name} "
                            f"{_lower_initial(self._creature_label(target_ref))}"
                        ),
                        "attack",
                        target_ref,
                        id=(
                            f"{creature_ref}-attack-{source_slug}-{attack_type}-"
                            f"{target_ref.replace(':', '-')}"
                        ),
                        creature_ref=creature_ref,
                        cost=ActionCost(
                            action=1 if enemy.attacks_remaining == 0 else 0
                        ),
                        source_trigger_id=(
                            enemy.pending_multiattack[0].name
                            if enemy.pending_multiattack
                            else None
                        ),
                        preferred_attack_type=attack_type,
                        preferred_attack_name=source.name,
                    )
                )
        actions.append(
            EncounterAction(
                f"Grapple {_lower_initial(self._creature_label(target_ref))}",
                "grapple",
                target_ref,
                id=f"{creature_ref}-grapple-{target_ref.replace(':', '-')}",
                creature_ref=creature_ref,
                cost=ActionCost(action=1 if enemy.attacks_remaining == 0 else 0),
            )
        )
    for definition in enemy.creature.stat_block_actions.values():
        if not isinstance(definition, AutomaticActionDefinition):
            continue
        target_refs = (
            [creature_ref]
            if definition.target.kind == "self"
            else [
                target_ref
                for target_ref in self._living_creature_refs()
                if self._creatures_are_opponents(creature_ref, target_ref)
            ]
            if definition.target.kind == "creature"
            else []
        )
        for target_ref in target_refs:
            target_suffix = (
                ""
                if target_ref == creature_ref
                else f" {_lower_initial(self._creature_label(target_ref))}"
            )
            source_slug = definition.name.lower().replace(" ", "-")
            actions.append(
                EncounterAction(
                    f"{definition.name}{target_suffix}",
                    "stat_block",
                    target_ref,
                    id=(
                        f"{creature_ref}-stat-block-{source_slug}-"
                        f"{target_ref.replace(':', '-')}"
                    ),
                    creature_ref=creature_ref,
                    preferred_attack_name=definition.name,
                    cost=ActionCost(action=1),
                )
            )
    actions.extend(self._available_feature_actions(enemy.creature))
    actions.extend(self._available_spell_actions(enemy.creature))
    actions.extend(available_escape_actions(self, creature_ref))
    if enemy.bonus_action_available:
        for item in healing_potions_in_inventory(
            enemy.creature,
            self.item_templates,
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
    return [action for action in actions if action_eligibility(self, creature_ref, action).allowed]


def execute_creature_action(
    self: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionResult:
    context = begin_action_execution(self, action, decision)
    enemy = self.creatures[context.actor_ref]
    progress = context.progress
    action_id = context.action_id
    action_ends_turn = action.kind == "wait"

    if action.kind == "move":
        direction = str(action.value)
        dx, dy = DIRECTION_DELTAS[direction]
        destination = Position(enemy.position.x + dx, enemy.position.y + dy)
        movement_cost = self._movement_cost_for(decision.creature_ref)
        if movement_cost is None:
            raise RuntimeError("Movement is unavailable for this creature.")
        remaining = max(
            0,
            (enemy.movement_remaining or 0) - movement_cost,
        )
        grappled_refs = self._grappling_targets_for(decision.creature_ref)
        grappled_positions = {
            target_ref: Position(
                self.creatures[target_ref].position.x + dx,
                self.creatures[target_ref].position.y + dy,
            )
            for target_ref in grappled_refs
        }
        if self.reaction_engine.queue_opportunity_attack(
            self,
            mover_ref=decision.creature_ref,
            action_id=action_id,
            direction=direction,
            from_position=Position(enemy.position.x, enemy.position.y),
            to_position=destination,
            remaining_movement_after=remaining,
            progress=progress,
            external_only=True,
            excluded_reactor_refs=grappled_refs,
        ):
            progress.paused_for_decision = True
            return ActionExecutionResult(
                context,
                ActionExecutionOutcome.PAUSE_FOR_REACTION,
            )
        progress.messages.extend(
            self.reaction_engine.resolve_automatic_opportunity_attacks(
                self,
                mover_ref=decision.creature_ref,
                from_position=Position(enemy.position.x, enemy.position.y),
                to_position=destination,
                action_id=action_id,
                progress=progress,
                excluded_reactor_refs=grappled_refs,
            )
        )
        if not enemy.is_alive:
            return ActionExecutionResult(
                context,
                ActionExecutionOutcome.CONTINUE_TURN,
            )
        enemy.position = destination
        for target_ref, target_position in grappled_positions.items():
            self.creatures[target_ref].position = target_position
        enemy.movement_remaining = remaining
        progress.messages.append(
            (
                "system",
                f"{enemy.creature.name} moves {direction} to ({destination.x}, {destination.y}).",
            )
        )
        progress.events.append(
            self._event(
                "movement_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={
                    "direction": direction,
                    "to": {"x": destination.x, "y": destination.y},
                },
            )
        )
    elif action.kind == "multiattack":
        resolve_multiattack_action(
            self,
            enemy.creature,
            progress,
            action_id,
        )
    elif action.kind == "attack":
        resolve_attack_action(
            self,
            enemy.creature,
            action,
            progress,
            action_id,
        )
    elif action.kind == "stat_block":
        from .actions.stat_block import resolve_automatic_action

        resolve_automatic_action(
            self,
            enemy.creature,
            action,
            progress,
            action_id,
        )
    elif action.kind == "feature":
        if not isinstance(action.value, str):
            raise ValueError("Feature action requires a feature id.")
        self._resolve_feature_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "grapple":
        self._resolve_grapple_action(
            enemy.creature,
            action,
            progress,
            action_id,
        )
    elif action.kind == "escape_grapple":
        resolve_escape_action(
            self,
            enemy.creature,
            action,
            progress,
            action_id,
        )
    elif action.kind == "utilize":
        if not isinstance(action.value, str):
            raise ValueError("Utilize action requires an item id.")
        self._resolve_utilize_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "spell":
        if not isinstance(action.value, str):
            raise ValueError("Spell action requires a spell payload.")
        self._resolve_spell_action(
            enemy.creature,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "wait":
        progress.messages.append(("system", f"{enemy.creature.name} waits."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "wait"},
            )
        )
    else:
        raise ValueError(f"Unsupported creature action: {action.kind}")

    progress.transition = self._check_transition()
    return finish_action_execution(
        context,
        action_ends_turn=action_ends_turn,
    )


def begin_action_execution(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionContext:
    require_action_eligible(state, decision.creature_ref, action)
    actor = state.creatures[decision.creature_ref]
    context = ActionExecutionContext(
        actor_ref=decision.creature_ref,
        actor=actor,
        decision=decision,
        action=action,
        action_id=state._next_action_id(),
    )
    context.progress.events.append(
        state._event(
            "action_declared",
            creature_ref=context.actor_ref,
            action_id=context.action_id,
            data={
                "kind": action.kind,
                "value": action.value,
                "selected_action_id": action.id,
            },
        )
    )
    return context


def finish_action_execution(
    context: ActionExecutionContext,
    *,
    action_ends_turn: bool,
) -> ActionExecutionResult:
    if context.progress.transition is not None:
        outcome = ActionExecutionOutcome.ENCOUNTER_COMPLETE
    elif action_ends_turn:
        outcome = ActionExecutionOutcome.END_TURN
    else:
        outcome = ActionExecutionOutcome.CONTINUE_TURN
    return ActionExecutionResult(context, outcome)
