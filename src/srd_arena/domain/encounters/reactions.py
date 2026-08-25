from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ..geometry import MovementBudget, Position
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
    CloseParentDecision,
    DamageRerollRequest,
    DecisionFrame,
    DecisionContinuation,
    DecisionExecutionResult,
    EncounterAction,
    EncounterProgress,
    OpportunityAttackRequest,
    PendingMovement,
    ResumeMovement,
)
from .ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)
from .refs import reroll_die_action_id as _reroll_die_action_id

if TYPE_CHECKING:
    from .encounter import EncounterState


def _roll_die(sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _resolve_attack_lifecycle(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    damage: int,
    progress: EncounterProgress,
) -> None:
    resolve_spell_lifecycle_event(
        state,
        "target_makes_attack",
        actor_ref=attacker_ref,
        target_ref=target_ref,
        progress=progress,
    )
    if damage > 0:
        resolve_spell_lifecycle_event(
            state,
            "target_damaged",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
        resolve_spell_lifecycle_event(
            state,
            "target_deals_damage",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
    resolve_concentration_damage(state, target_ref, damage, progress)


def _roll_dice(count: int, sides: int) -> int:
    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def _damage_reroll_request(decision: DecisionFrame) -> DamageRerollRequest:
    if not isinstance(decision.request, DamageRerollRequest):
        raise RuntimeError(
            f"Decision '{decision.id}' does not contain a damage reroll request."
        )
    return decision.request


def _opportunity_attack_request(decision: DecisionFrame) -> OpportunityAttackRequest:
    if not isinstance(decision.request, OpportunityAttackRequest):
        raise RuntimeError(
            f"Decision '{decision.id}' does not contain an opportunity attack request."
        )
    return decision.request


class ReactionEngine:
    """Resolve interrupts while the orchestrator owns parent continuation."""

    def resolve_automatic_opportunity_attacks(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        from_position: Position,
        to_position: Position,
        action_id: str,
        progress: EncounterProgress,
        excluded_reactor_refs: Collection[str] = (),
    ) -> list[tuple[str, str]]:
        mover = state.creatures[mover_ref]
        messages: list[tuple[str, str]] = []
        reactors = [
            (reactor_ref, reactor)
            for reactor_ref, reactor in state.creatures.items()
            if reactor_ref != mover_ref
            and reactor_ref not in excluded_reactor_refs
            and reactor.is_alive
            and state._creatures_are_opponents(reactor_ref, mover_ref)
            and state._creature_controller(reactor_ref) == "scripted"
            and state.combat_rules.reaction_eligibility(
                state,
                reactor_ref,
            ).allowed
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
                automatic_critical_provider_ids=(
                    state._automatic_critical_provider_ids_for(
                        reactor_ref,
                        mover_ref,
                    )
                ),
            )
            apply_attack_damage(
                attack,
                mover.creature,
                attacker_label=reactor.creature.name,
                target_label=mover.creature.name,
            )
            _resolve_attack_lifecycle(
                state,
                attacker_ref=reactor_ref,
                target_ref=mover_ref,
                damage=attack.damage,
                progress=progress,
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
        continuation: DecisionContinuation | None = None,
        reaction: bool = False,
    ) -> None:
        frame_id = state._next_frame_id()
        current_frame = state.current_decision()
        request = DamageRerollRequest(
            action_id=action_id,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            attacker_label=attacker_label,
            target_label=target_label,
            attacks_remaining=state.active_attacks_remaining,
            attack=attack,
            triggered_effect=triggered_effect,
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
                request=request,
                continuation=continuation,
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
                data=self.damage_reroll_event_data(request),
            )
        )
        progress.paused_for_decision = True

    def reroll_damage_actions(self, state: EncounterState) -> list[EncounterAction]:
        request = _damage_reroll_request(state.current_decision())
        if request.attack.damage_roll is None:
            return []
        actions = [
            EncounterAction(
                f"Reroll damage die {index + 1} ({request.attack.damage_roll.dice[index].result})",
                "reroll_die",
                index,
                id=_reroll_die_action_id(request.action_id, index),
                creature_ref=request.attacker_ref,
            )
            for index in reroll_eligible_indices(
                request.triggered_effect,
                request.attack.damage_roll,
            )
        ]
        actions.append(
            EncounterAction(
                "Use current damage",
                "accept_roll",
                id=f"{request.action_id}-accept-damage",
                creature_ref=request.attacker_ref,
            )
        )
        return actions

    def apply_damage_reroll_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        request = _damage_reroll_request(decision)
        if request.attack.damage_roll is None:
            raise RuntimeError("Damage reroll requested without a pending attack.")
        progress = EncounterProgress()
        progress.events.append(
            state._event(
                "action_declared",
                creature_ref=request.attacker_ref,
                frame_id=decision.id,
                action_id=request.action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "reroll_die":
            if not isinstance(action.value, int):
                raise ValueError("Reroll die action requires an integer die index.")
            eligible = reroll_eligible_indices(
                request.triggered_effect,
                request.attack.damage_roll,
            )
            if action.value not in eligible:
                raise ValueError(f"Damage die {action.value} is not eligible for reroll.")
            previous = request.attack.damage_roll.dice[action.value].result
            request.attack.damage_roll = reroll_dice(
                request.attack.damage_roll,
                [action.value],
                roller=lambda sides: _roll_dice(1, sides),
            )
            replacement = request.attack.damage_roll.dice[action.value].result
            request.attack.damage_roll_detail = damage_roll_detail(request.attack)
            progress.messages.append(
                (
                    "system",
                    f"Damage die {action.value + 1} rerolled: {previous} -> {replacement}.",
                )
            )
            progress.events.append(
                state._event(
                    "damage_rerolled",
                    creature_ref=request.attacker_ref,
                    frame_id=decision.id,
                    action_id=request.action_id,
                    data=self.damage_reroll_event_data(request),
                )
            )
            if reroll_eligible_indices(
                request.triggered_effect,
                request.attack.damage_roll,
            ):
                progress.paused_for_decision = True
                return DecisionExecutionResult(
                    progress=progress,
                    action_id=request.action_id,
                    completed=False,
                )
        elif action.kind != "accept_roll":
            raise ValueError(f"Unsupported damage reroll action: {action.kind}")

        self.finalize_damage_reroll(state, request, progress, decision)
        return DecisionExecutionResult(
            progress=progress,
            action_id=request.action_id,
            completed=True,
        )

    def finalize_damage_reroll(
        self,
        state: EncounterState,
        request: DamageRerollRequest,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        attacker = state.creatures[request.attacker_ref].creature
        target = state.creatures[request.target_ref]
        apply_attack_damage(
            request.attack,
            target.creature,
            attacker_label=attacker.name,
            target_label=request.target_label,
        )
        _resolve_attack_lifecycle(
            state,
            attacker_ref=request.attacker_ref,
            target_ref=request.target_ref,
            damage=request.attack.damage,
            progress=progress,
        )
        progress.messages.extend(request.attack.messages)
        progress.events.append(
            state._event(
                "attack_resolved",
                creature_ref=request.attacker_ref,
                frame_id=decision.id,
                action_id=request.action_id,
                data={
                    **self.damage_reroll_event_data(request),
                    "hit": True,
                    "damage": request.attack.damage,
                    "damage_roll_detail": request.attack.damage_roll_detail,
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
                    creature_ref=request.target_ref,
                    frame_id=decision.id,
                    action_id=request.action_id,
                )
            )

    def damage_reroll_event_data(
        self,
        request: DamageRerollRequest,
    ) -> dict[str, object]:
        if request.attack.damage_roll is None:
            return {}
        eligible = reroll_eligible_indices(
            request.triggered_effect,
            request.attack.damage_roll,
        )
        return {
            "attacker_label": request.attacker_label,
            "target_ref": request.target_ref,
            "target_label": request.target_label,
            "attacks_remaining": request.attacks_remaining,
            "attack_roll": request.attack.attack_roll,
            "attack_roll_detail": request.attack.attack_roll_detail,
            "hit": True,
            "critical_hit": request.attack.critical_hit,
            "damage": 0,
            "damage_roll_detail": damage_roll_detail(request.attack),
            "roll_id": f"{request.action_id}:damage",
            "triggered_effect_id": request.triggered_effect.id,
            "eligible_die_indices": list(eligible),
            "reroll_action_ids": {
                str(index): _reroll_die_action_id(request.action_id, index)
                for index in eligible
            },
            "accept_action_id": f"{request.action_id}-accept-damage",
            "reaction": request.reaction,
        }

    def apply_reaction_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        progress = EncounterProgress()
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
            request = _opportunity_attack_request(decision)
            movement = request.movement
            eligibility = state.combat_rules.reaction_eligibility(
                state,
                reactor_ref,
            )
            if not eligibility.allowed:
                raise ValueError(eligibility.failures[0].message)
            reactor.reaction_available = False
            target_ref = movement.creature_ref
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
                automatic_critical_provider_ids=(
                    state._automatic_critical_provider_ids_for(
                        reactor_ref,
                        target_ref,
                    )
                ),
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
                    continuation=CloseParentDecision(
                        frame_id=decision.id,
                        action_id=resolved_action_id,
                    ),
                    reaction=True,
                )
                return DecisionExecutionResult(
                    progress=progress,
                    action_id=resolved_action_id,
                    completed=False,
                )
            apply_attack_damage(
                attack,
                target.creature,
                attacker_label=reactor_label,
                target_label=target_label,
            )
            _resolve_attack_lifecycle(
                state,
                attacker_ref=reactor_ref,
                target_ref=target_ref,
                damage=attack.damage,
                progress=progress,
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
                        creature_ref=movement.creature_ref,
                        frame_id=decision.id,
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind != "pass":
            raise ValueError(f"Unsupported reaction action: {action.kind}")

        return DecisionExecutionResult(
            progress=progress,
            action_id=resolved_action_id,
            completed=True,
        )

    def resume_movement(
        self,
        state: EncounterState,
        movement: PendingMovement,
        progress: EncounterProgress,
    ) -> None:
        mover = state.creatures[movement.creature_ref]
        if mover.is_alive and state._position_is_free(
            movement.to_position.x,
            movement.to_position.y,
            ignored_refs={movement.creature_ref},
        ):
            mover.position = Position(
                movement.to_position.x,
                movement.to_position.y,
            )
            for target_ref, target_position in movement.companion_destinations.items():
                state.creatures[target_ref].position = Position(
                    target_position.x,
                    target_position.y,
                )
            progress.messages.append(
                (
                    "system",
                    f"{mover.creature.name} moves {movement.direction} to "
                    f"({movement.to_position.x}, {movement.to_position.y}).",
                )
            )
            progress.events.append(
                state._event(
                    "movement_resolved",
                    creature_ref=movement.creature_ref,
                    action_id=movement.action_id,
                    data={
                        "direction": movement.direction,
                        "to": {
                            "x": movement.to_position.x,
                            "y": movement.to_position.y,
                        },
                        "resumed": True,
                    },
                )
            )

        mover.movement_remaining = movement.remaining_movement_after

    def queue_opportunity_attack(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: MovementBudget,
        companion_destinations: dict[str, Position],
        progress: EncounterProgress,
        external_only: bool,
        excluded_reactor_refs: Collection[str] = (),
    ) -> bool:
        reactors = [
            (creature_ref, creature_state)
            for creature_ref, creature_state in state.creatures.items()
            if creature_ref != mover_ref
            and creature_ref not in excluded_reactor_refs
            and creature_state.is_alive
            and state._creatures_are_opponents(creature_ref, mover_ref)
            and (
                not external_only
                or state._creature_controller(creature_ref) == "external"
            )
            and state.combat_rules.reaction_eligibility(
                state,
                creature_ref,
            ).allowed
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
        movement = PendingMovement(
            action_id=action_id,
            creature_ref=mover_ref,
            direction=direction,
            from_position=Position(from_position.x, from_position.y),
            to_position=Position(to_position.x, to_position.y),
            remaining_movement_after=remaining_movement_after,
            trigger_id=trigger_id,
            companion_destinations={
                target_ref: Position(position.x, position.y)
                for target_ref, position in companion_destinations.items()
            },
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
                request=OpportunityAttackRequest(movement),
                continuation=ResumeMovement(movement),
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
        decision = state.current_decision()
        if not isinstance(decision.request, OpportunityAttackRequest):
            creature_ref = decision.creature_ref
            return [
                EncounterAction(
                    "Pass reaction",
                    "pass",
                    id=f"{creature_ref}-reaction-pass",
                    creature_ref=creature_ref,
                    cost=ActionCost(),
                )
            ]

        movement = decision.request.movement
        target_ref = movement.creature_ref
        target = state.creatures[target_ref]
        reactor_ref = decision.creature_ref
        actions: list[EncounterAction] = []
        if (
            state.combat_rules.reaction_eligibility(
                state,
                reactor_ref,
            ).allowed
            and target.is_alive
        ):
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
                    source_trigger_id=movement.trigger_id,
                    cost=ActionCost(reaction=1),
                )
            )
        actions.append(
            EncounterAction(
                "Pass reaction",
                "pass",
                id=f"{reactor_ref}-reaction-pass",
                creature_ref=reactor_ref,
                source_trigger_id=movement.trigger_id,
            )
        )
        return actions


REACTION_ENGINE = ReactionEngine()
