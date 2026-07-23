from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from ..geometry import Position
from ..rolls.dice import reroll_dice
from ..effects.triggered import TriggeredEffect, reroll_eligible_indices
from .actions.attack_resolution import (
    apply_attack_damage,
    can_make_opportunity_attack,
    damage_roll_detail,
    matching_damage_reroll_rule,
    resolve_attack,
)
from .behaviors import is_adjacent as _is_adjacent
from .models import (
    ActionCost,
    AttackOutcome,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
    PendingAction,
    PendingAttack,
)
from .refs import reroll_die_action_id as _reroll_die_action_id

if TYPE_CHECKING:
    from .encounter import EncounterState


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


class ReactionEngine:
    def resolve_automatic_opportunity_attacks(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        from_position: Position,
        to_position: Position,
        action_id: str,
        progress: EncounterProgress,
    ) -> list[tuple[str, str]]:
        mover = state.creatures[mover_ref]
        messages: list[tuple[str, str]] = []
        reactors = [
            (reactor_ref, reactor)
            for reactor_ref, reactor in state.creatures.items()
            if reactor_ref != mover_ref
            and reactor.is_alive
            and state._creatures_are_opponents(reactor_ref, mover_ref)
            and state._creature_controller(reactor_ref) == "ai"
            and reactor.reaction_available
            and can_make_opportunity_attack(
                reactor.creature,
                state.item_templates,
            )
            and _is_adjacent(from_position, reactor.position)
            and not _is_adjacent(to_position, reactor.position)
        ]
        for reactor_ref, reactor in reactors:
            reactor.reaction_available = False
            attack = resolve_attack(
                reactor.creature,
                mover.creature,
                attacker_label=reactor.creature.name,
                target_label=mover.creature.name,
                action_label="Opportunity attack",
                items_by_id=state.item_templates,
                attacker_position=reactor.position,
                nearby_opponent_positions=(mover.position,),
                preferred_attack_type="melee",
                attack_roll_mode_override=state._attack_roll_mode_for(
                    reactor_ref,
                    mover_ref,
                    "melee",
                    reactor.position,
                    (mover.position,),
                ),
                d20_roller=_roll_die,
                dice_roller=_roll_dice,
            )
            apply_attack_damage(
                attack,
                mover.creature,
                attacker_label=reactor.creature.name,
                target_label=mover.creature.name,
            )
            messages.extend(attack.messages)
            progress.events.append(
                state._event(
                    "attack_resolved",
                    creature_ref=reactor_ref,
                    action_id=action_id,
                    data={
                        "attacker_label": reactor.creature.name,
                        "target_ref": mover_ref,
                        "target_label": mover.creature.name,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if not mover.is_alive:
                break
        return messages

    def open_damage_reroll_decision(
        self,
        state: EncounterState,
        *,
        attack: AttackOutcome,
        triggered_effect: TriggeredEffect,
        attacker_ref: str,
        target_ref: str,
        attacker_label: str,
        target_label: str,
        action_id: str,
        progress: EncounterProgress,
        continuation: str = "return_to_turn",
        reaction: bool = False,
    ) -> None:
        frame_id = state._next_frame_id()
        current_frame = state.current_decision()
        state.pending_attack = PendingAttack(
            action_id=action_id,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            attacker_label=attacker_label,
            target_label=target_label,
            attacks_remaining=state.active_attacks_remaining,
            attack=attack,
            triggered_effect=triggered_effect,
            continuation=continuation,
            reaction=reaction,
        )
        state.decision_stack.append(
            DecisionFrame(
                id=frame_id,
                creature_ref=attacker_ref,
                kind="reroll_dice",
                reason=triggered_effect.id,
                parent_frame_id=current_frame.id,
                parent_action_id=action_id,
                can_pass=True,
            )
        )
        progress.messages.extend(attack.messages)
        attack.messages = []
        progress.messages.append(
            (
                "system",
                f"{triggered_effect.id.replace('_', ' ').title()} can reroll qualifying damage dice.",
            )
        )
        progress.events.append(
            state._event(
                "attack_pending",
                creature_ref=attacker_ref,
                frame_id=frame_id,
                action_id=action_id,
                data=self.pending_attack_event_data(state),
            )
        )
        progress.paused_for_decision = True

    def reroll_damage_actions(self, state: EncounterState) -> list[EncounterAction]:
        pending = state.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            return []
        actions = [
            EncounterAction(
                f"Reroll damage die {index + 1} ({pending.attack.damage_roll.dice[index].result})",
                "reroll_die",
                index,
                id=_reroll_die_action_id(pending.action_id, index),
                creature_ref=pending.attacker_ref,
            )
            for index in reroll_eligible_indices(
                pending.triggered_effect,
                pending.attack.damage_roll,
            )
        ]
        actions.append(
            EncounterAction(
                "Use current damage",
                "accept_roll",
                id=f"{pending.action_id}-accept-damage",
                creature_ref=pending.attacker_ref,
            )
        )
        return actions

    def apply_damage_reroll_action(
        self,
        state: EncounterState,
        player: Creature,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        pending = state.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            raise RuntimeError("Damage reroll requested without a pending attack.")
        progress = EncounterProgress()
        progress.events.append(
            state._event(
                "action_declared",
                creature_ref=pending.attacker_ref,
                frame_id=decision.id,
                action_id=pending.action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "reroll_die":
            if not isinstance(action.value, int):
                raise ValueError("Reroll die action requires an integer die index.")
            eligible = reroll_eligible_indices(
                pending.triggered_effect,
                pending.attack.damage_roll,
            )
            if action.value not in eligible:
                raise ValueError(f"Damage die {action.value} is not eligible for reroll.")
            previous = pending.attack.damage_roll.dice[action.value].result
            pending.attack.damage_roll = reroll_dice(
                pending.attack.damage_roll,
                [action.value],
                roller=lambda sides: _roll_dice(1, sides),
            )
            replacement = pending.attack.damage_roll.dice[action.value].result
            pending.attack.damage_roll_detail = damage_roll_detail(pending.attack)
            progress.messages.append(
                (
                    "system",
                    f"Damage die {action.value + 1} rerolled: {previous} -> {replacement}.",
                )
            )
            progress.events.append(
                state._event(
                    "damage_rerolled",
                    creature_ref=pending.attacker_ref,
                    frame_id=decision.id,
                    action_id=pending.action_id,
                    data=self.pending_attack_event_data(state),
                )
            )
            if reroll_eligible_indices(
                pending.triggered_effect,
                pending.attack.damage_roll,
            ):
                progress.paused_for_decision = True
                return progress
        elif action.kind != "accept_roll":
            raise ValueError(f"Unsupported damage reroll action: {action.kind}")

        self.finalize_pending_attack(state, player, progress, decision)
        return progress

    def finalize_pending_attack(
        self,
        state: EncounterState,
        player: Creature,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        pending = state.pending_attack
        if pending is None:
            raise RuntimeError("Cannot finalize an attack that is not pending.")
        attacker = state.creatures[pending.attacker_ref].creature
        target = state.creatures[pending.target_ref]
        apply_attack_damage(
            pending.attack,
            target.creature,
            attacker_label=attacker.name,
            target_label=pending.target_label,
        )
        progress.messages.extend(pending.attack.messages)
        progress.events.append(
            state._event(
                "attack_resolved",
                creature_ref=pending.attacker_ref,
                frame_id=decision.id,
                action_id=pending.action_id,
                data={
                    **self.pending_attack_event_data(state),
                    "hit": True,
                    "damage": pending.attack.damage,
                    "damage_roll_detail": pending.attack.damage_roll_detail,
                    "eligible_die_indices": [],
                    "reroll_action_ids": {},
                    "accept_action_id": None,
                },
            )
        )
        if not target.is_alive:
            progress.events.append(
                state._event(
                    "creature_defeated",
                    creature_ref=pending.target_ref,
                    frame_id=decision.id,
                    action_id=pending.action_id,
                )
            )
        state.pending_attack = None
        state.decision_stack.pop()
        progress.events.append(
            state._event(
                "decision_closed",
                creature_ref=pending.attacker_ref,
                frame_id=decision.id,
                action_id=pending.action_id,
            )
        )
        progress.transition = state.turn_engine.check_transition(state)
        if (
            pending.continuation == "complete_reaction"
            and progress.transition is None
            and player.get_health() > 0
        ):
            self.complete_parent_reaction(state, player, progress, pending.action_id)

    def complete_parent_reaction(
        self,
        state: EncounterState,
        player: Creature,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        reaction = state.current_decision()
        if reaction.kind != "reaction":
            raise RuntimeError(
                "Pending attack expected to resume a reaction, "
                f"but current decision is '{reaction.kind}'."
            )
        state.decision_stack.pop()
        progress.events.append(
            state._event(
                "decision_closed",
                creature_ref=reaction.creature_ref,
                frame_id=reaction.id,
                action_id=action_id,
            )
        )
        self.resume_pending_action(state, player, progress)
        progress.transition = state.turn_engine.check_transition(state)
        if progress.transition is not None or player.get_health() <= 0:
            return
        follow_up = state.turn_engine.advance_until_next_decision(state, player)
        state._merge_progress(progress, follow_up)

    def pending_attack_event_data(self, state: EncounterState) -> dict[str, object]:
        pending = state.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            return {}
        eligible = reroll_eligible_indices(
            pending.triggered_effect,
            pending.attack.damage_roll,
        )
        return {
            "attacker_label": pending.attacker_label,
            "target_ref": pending.target_ref,
            "target_label": pending.target_label,
            "attacks_remaining": pending.attacks_remaining,
            "attack_roll": pending.attack.attack_roll,
            "attack_roll_detail": pending.attack.attack_roll_detail,
            "hit": True,
            "critical_hit": pending.attack.critical_hit,
            "damage": 0,
            "damage_roll_detail": damage_roll_detail(pending.attack),
            "roll_id": f"{pending.action_id}:damage",
            "triggered_effect_id": pending.triggered_effect.id,
            "eligible_die_indices": list(eligible),
            "reroll_action_ids": {
                str(index): _reroll_die_action_id(pending.action_id, index)
                for index in eligible
            },
            "accept_action_id": f"{pending.action_id}-accept-damage",
            "reaction": pending.reaction,
        }

    def apply_reaction_action(
        self,
        state: EncounterState,
        player: Creature,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        progress = EncounterProgress()
        pending_action = state.pending_action
        if pending_action is None:
            raise RuntimeError("Reaction action requested without a pending action.")
        resolved_action_id = state._next_action_id()

        reactor_ref = decision.creature_ref
        reactor = state.creatures[reactor_ref]
        progress.events.append(
            state._event(
                "action_declared",
                creature_ref=reactor_ref,
                frame_id=decision.id,
                action_id=resolved_action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "opportunity_attack":
            reactor.reaction_available = False
            target_ref = pending_action.creature_ref
            target = state.creatures[target_ref]
            target_label = state._creature_label(target_ref)
            reactor_label = state._creature_label(reactor_ref)
            attack = resolve_attack(
                reactor.creature,
                target.creature,
                attacker_label=reactor_label,
                target_label=target_label,
                action_label="Opportunity attack",
                items_by_id=state.item_templates,
                attacker_position=reactor.position,
                nearby_opponent_positions=(target.position,),
                preferred_attack_type="melee",
                attack_roll_mode_override=state._attack_roll_mode_for(
                    reactor_ref,
                    target_ref,
                    "melee",
                    reactor.position,
                    (target.position,),
                ),
                d20_roller=_roll_die,
                dice_roller=_roll_dice,
            )
            reroll_rule = matching_damage_reroll_rule(reactor.creature, attack)
            if attack.hit and reroll_rule is not None:
                self.open_damage_reroll_decision(
                    state,
                    attack=attack,
                    triggered_effect=reroll_rule,
                    attacker_ref=reactor_ref,
                    target_ref=target_ref,
                    attacker_label=reactor_label,
                    target_label=target_label,
                    action_id=resolved_action_id,
                    progress=progress,
                    continuation="complete_reaction",
                    reaction=True,
                )
                return progress
            apply_attack_damage(
                attack,
                target.creature,
                attacker_label=reactor_label,
                target_label=target_label,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                state._event(
                    "attack_resolved",
                    creature_ref=reactor_ref,
                    frame_id=decision.id,
                    action_id=resolved_action_id,
                    data={
                        "attacker_label": reactor_label,
                        "target_ref": target_ref,
                        "target_label": target_label,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if not target.is_alive:
                progress.events.append(
                    state._event(
                        "creature_defeated",
                        creature_ref=pending_action.creature_ref,
                        frame_id=decision.id,
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind != "pass":
            raise ValueError(f"Unsupported reaction action: {action.kind}")

        state.decision_stack.pop()
        progress.events.append(
            state._event(
                "decision_closed",
                creature_ref=reactor_ref,
                frame_id=decision.id,
                action_id=resolved_action_id,
            )
        )

        self.resume_pending_action(state, player, progress)
        progress.transition = state.turn_engine.check_transition(state)
        if progress.transition is not None or player.get_health() <= 0:
            return progress

        follow_up = state.turn_engine.advance_until_next_decision(state, player)
        state._merge_progress(progress, follow_up)
        return progress

    def resume_pending_action(
        self,
        state: EncounterState,
        player: Creature,
        progress: EncounterProgress,
    ) -> None:
        pending_action = state.pending_action
        if pending_action is None:
            return
        state.pending_action = None
        if pending_action.kind != "move":
            return
        mover = state.creatures[pending_action.creature_ref]
        if mover.is_alive and state._position_is_free(
            pending_action.to_position.x,
            pending_action.to_position.y,
            ignored_refs={pending_action.creature_ref},
        ):
            mover.position = Position(
                pending_action.to_position.x,
                pending_action.to_position.y,
            )
            progress.messages.append(
                (
                    "system",
                    f"{mover.creature.name} moves {pending_action.direction} to "
                    f"({pending_action.to_position.x}, {pending_action.to_position.y}).",
                )
            )
            progress.events.append(
                state._event(
                    "movement_resolved",
                    creature_ref=pending_action.creature_ref,
                    action_id=pending_action.id,
                    data={
                        "direction": pending_action.direction,
                        "to": {
                            "x": pending_action.to_position.x,
                            "y": pending_action.to_position.y,
                        },
                        "resumed": True,
                    },
                )
            )

        if pending_action.creature_ref == state.primary_creature_ref:
            mover.movement_remaining = pending_action.remaining_movement_after
            return
        if state._creature_controller(pending_action.creature_ref) == "user":
            mover.movement_remaining = pending_action.remaining_movement_after
            return
        mover.movement_remaining = pending_action.remaining_movement_after
        if state.ai_action_limit is not None:
            return
        completed_turn, resumed, _ = state.turn_engine.run_creature_turn(
            state,
            player,
            pending_action.creature_ref,
        )
        state._merge_progress(progress, resumed)
        if completed_turn and not progress.paused_for_decision:
            state.turn_engine.advance_turn(state)
            state.turn_engine.maybe_reset_reactions(state)

    def queue_opportunity_attack(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: int,
        progress: EncounterProgress,
        user_controlled_only: bool,
    ) -> bool:
        reactors = [
            (creature_ref, creature_state)
            for creature_ref, creature_state in state.creatures.items()
            if creature_ref != mover_ref
            and creature_state.is_alive
            and state._creatures_are_opponents(creature_ref, mover_ref)
            and (
                not user_controlled_only
                or state._creature_controller(creature_ref) == "user"
            )
            and creature_state.reaction_available
            and can_make_opportunity_attack(
                creature_state.creature,
                state.item_templates,
            )
            and _is_adjacent(from_position, creature_state.position)
            and not _is_adjacent(to_position, creature_state.position)
        ]
        if not reactors:
            return False
        reactor_ref, _reactor = reactors[0]

        frame_id = state._next_frame_id()
        trigger_id = state._next_frame_id(prefix="trigger")
        current_frame = state.current_decision()
        state.pending_action = PendingAction(
            id=action_id,
            kind="move",
            creature_ref=mover_ref,
            direction=direction,
            from_position=Position(from_position.x, from_position.y),
            to_position=Position(to_position.x, to_position.y),
            remaining_movement_after=remaining_movement_after,
            trigger_id=trigger_id,
        )
        state.decision_stack.append(
            DecisionFrame(
                id=frame_id,
                creature_ref=reactor_ref,
                kind="reaction",
                reason="opportunity_attack",
                parent_frame_id=current_frame.id,
                parent_action_id=action_id,
                can_pass=True,
            )
        )
        progress.events.append(
            state._event(
                "trigger_opened",
                creature_ref=reactor_ref,
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "kind": "opportunity_attack",
                    "target_ref": mover_ref,
                    "trigger_id": trigger_id,
                },
            )
        )
        return True

    def reaction_actions(self, state: EncounterState) -> list[EncounterAction]:
        pending_action = state.pending_action
        if pending_action is None or pending_action.kind != "move":
            creature_ref = state.current_decision().creature_ref
            return [
                EncounterAction(
                    "Pass reaction",
                    "pass",
                    id=f"{creature_ref}-reaction-pass",
                    creature_ref=creature_ref,
                    cost=ActionCost(),
                )
            ]

        target_ref = pending_action.creature_ref
        target = state.creatures[target_ref]
        reactor_ref = state.current_decision().creature_ref
        reactor = state.creatures[reactor_ref]
        actions: list[EncounterAction] = []
        if reactor.reaction_available and target.is_alive:
            actions.append(
                EncounterAction(
                    f"Opportunity attack {target.creature.name}",
                    "opportunity_attack",
                    target_ref,
                    id=(
                        f"{reactor_ref}-opportunity-attack-"
                        f"{target_ref.replace(':', '-')}"
                    ),
                    creature_ref=reactor_ref,
                    source_trigger_id=pending_action.trigger_id,
                    cost=ActionCost(reaction=1),
                )
            )
        actions.append(
            EncounterAction(
                "Pass reaction",
                "pass",
                id=f"{reactor_ref}-reaction-pass",
                creature_ref=reactor_ref,
                source_trigger_id=pending_action.trigger_id,
            )
        )
        return actions


REACTION_ENGINE = ReactionEngine()
