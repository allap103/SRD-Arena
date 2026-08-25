"""Discover, offer, resolve, and continue Opportunity Attacks."""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING

from ...geometry import MovementBudget, Position
from ..actions.attack_resolution import (
    apply_attack_damage,
    can_make_opportunity_attack,
    matching_damage_reroll_rule,
    resolve_attack,
)
from ..behaviors import is_adjacent as _is_adjacent
from ..models import (
    ActionCost,
    CloseParentDecision,
    DecisionExecutionResult,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
    OpportunityAttackRequest,
    PendingMovement,
    ResumeMovement,
)
from .attack_lifecycle import resolve_attack_lifecycle
from .rolls import roll_dice, roll_die

if TYPE_CHECKING:
    from ..encounter import EncounterState


def opportunity_attack_request(decision: DecisionFrame) -> OpportunityAttackRequest:
    """Read and type-check the request owned by a reaction frame."""

    if not isinstance(decision.request, OpportunityAttackRequest):
        raise RuntimeError(
            f"Decision '{decision.id}' does not contain an opportunity "
            "attack request."
        )
    return decision.request


def resolve_automatic_opportunity_attacks(
    state: EncounterState,
    *,
    mover_ref: str,
    from_position: Position,
    to_position: Position,
    action_id: str,
    progress: EncounterProgress,
    excluded_reactor_refs: Collection[str] = (),
) -> list[tuple[str, str]]:
    """Resolve eligible scripted reactions without opening decision frames."""

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
            d20_roller=roll_die,
            dice_roller=roll_dice,
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
        resolve_attack_lifecycle(
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


def apply_reaction_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    *,
    open_damage_reroll: Callable[..., None],
) -> DecisionExecutionResult:
    """Resolve an Opportunity Attack or pass without closing its frame."""

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
        request = opportunity_attack_request(decision)
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
            d20_roller=roll_die,
            dice_roller=roll_dice,
            automatic_critical_provider_ids=(
                state._automatic_critical_provider_ids_for(
                    reactor_ref,
                    target_ref,
                )
            ),
        )
        reroll_rule = matching_damage_reroll_rule(reactor.creature, attack)
        if attack.hit and reroll_rule is not None:
            open_damage_reroll(
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
        resolve_attack_lifecycle(
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
    state: EncounterState,
    movement: PendingMovement,
    progress: EncounterProgress,
) -> None:
    """Resume the exact movement occurrence suspended by a reaction frame."""

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
    """Push the first eligible external Opportunity Attack decision."""

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


def reaction_actions(state: EncounterState) -> list[EncounterAction]:
    """Build the choices for the active reaction frame."""

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

