"""Resolve automatic and externally selected Opportunity Attacks."""

from __future__ import annotations

from collections.abc import Callable, Collection
from functools import partial
from typing import TYPE_CHECKING

from ...geometry import Position
from ..actions.attack_resolution import (
    apply_attack_damage,
    can_make_opportunity_attack,
    matching_damage_reroll_rule,
    resolve_attack,
)
from ..behaviors import is_adjacent as _is_adjacent
from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import (
    CloseParentDecision,
    DecisionFrame,
    OpportunityAttackRequest,
)
from ..encounter_models.resolution import (
    DecisionExecutionResult,
    EncounterProgress,
)
from ..participants import creature_controller, creatures_are_opponents
from ..state_combat import attack_roll_mode_for, automatic_critical_provider_ids_for
from ..state_runtime import create_event, creature_label, next_action_id
from .attack_lifecycle import resolve_attack_lifecycle

if TYPE_CHECKING:
    from ..encounter import EncounterState


def opportunity_attack_request(decision: DecisionFrame) -> OpportunityAttackRequest:
    """Read and type-check the request owned by a reaction frame.

    >>> from unittest.mock import Mock
    >>> request = Mock(spec=OpportunityAttackRequest)
    >>> frame = DecisionFrame("reaction", "guard", "reaction", "opportunity")
    >>> frame.request = request
    >>> opportunity_attack_request(frame) is request
    True
    >>> frame.request = None
    >>> opportunity_attack_request(frame)
    Traceback (most recent call last):
    ...
    RuntimeError: Decision 'reaction' does not contain an opportunity attack request.
    """

    if not isinstance(decision.request, OpportunityAttackRequest):
        raise RuntimeError(
            f"Decision '{decision.id}' does not contain an opportunity attack request."
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
    """Resolve eligible scripted reactions without opening decision frames.

    >>> from types import SimpleNamespace
    >>> mover = SimpleNamespace()
    >>> dice = SimpleNamespace(
    ...     roll_die=lambda _sides: 1,
    ...     roll_dice=lambda count, _sides: count,
    ... )
    >>> state = SimpleNamespace(creatures={"hero": mover}, dice=dice)
    >>> resolve_automatic_opportunity_attacks(
    ...     state, mover_ref="hero", from_position=Position(0, 0),
    ...     to_position=Position(1, 0), action_id="move-1",
    ...     progress=EncounterProgress(),
    ... )
    []
    """

    mover = state.creatures[mover_ref]
    roll_die = state.dice.roll_die
    roll_dice = state.dice.roll_dice
    messages: list[tuple[str, str]] = []
    reactors = [
        (reactor_ref, reactor)
        for reactor_ref, reactor in state.creatures.items()
        if reactor_ref != mover_ref
        and reactor_ref not in excluded_reactor_refs
        and reactor.is_alive
        and creatures_are_opponents(state, reactor_ref, mover_ref)
        and creature_controller(state, reactor_ref) == "scripted"
        and state.combat_rules.reaction_eligibility(
            state,
            reactor_ref,
            "opportunity_attack",
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
        attack_roll_rules = state.combat_rules.roll_modifiers(
            state,
            reactor_ref,
            "attack_roll",
        )
        damage_roll_rules = state.combat_rules.roll_modifiers(
            state,
            reactor_ref,
            "damage_roll",
        )
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
            attack_roll_mode_override=attack_roll_mode_for(
                state,
                reactor_ref,
                mover_ref,
                "melee",
                reactor.position,
                (mover.position,),
            ),
            sourced_attack_modifier=attack_roll_rules.resolve_modifier(roll_die),
            sourced_attack_roll_mode=attack_roll_rules.mode,
            target_armor_class=state.combat_rules.effective_armor_class(
                state,
                mover_ref,
            ).value,
            sourced_damage_modifier_for=partial(
                damage_roll_rules.resolve_modifier,
                roll_die,
            ),
            d20_roller=roll_die,
            dice_roller=roll_dice,
            automatic_critical_provider_ids=(
                automatic_critical_provider_ids_for(
                    state,
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
            create_event(
                state,
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
    """Resolve an Opportunity Attack or pass without closing its frame.

    Passing completes the decision without consuming the reactor's reaction.

    >>> from types import SimpleNamespace
    >>> frame = DecisionFrame("reaction", "guard", "reaction", "opportunity")
    >>> state = SimpleNamespace(
    ...     creatures={"guard": SimpleNamespace(reaction_available=True)},
    ...     action_sequence=1, event_sequence=1,
    ... )
    >>> result = apply_reaction_action(
    ...     state,
    ...     EncounterAction("Pass reaction", "pass", id="pass"),
    ...     frame,
    ...     open_damage_reroll=lambda *args, **kwargs: None,
    ... )
    >>> (result.completed, result.action_id, state.creatures["guard"].reaction_available)
    (True, 'action_1', True)
    """

    progress = EncounterProgress()
    resolved_action_id = next_action_id(state)

    reactor_ref = decision.creature_ref
    reactor = state.creatures[reactor_ref]
    progress.events.append(
        create_event(
            state,
            "action_declared",
            creature_ref=reactor_ref,
            frame_id=decision.id,
            action_id=resolved_action_id,
            data={"kind": action.kind, "selected_action_id": action.id},
        )
    )

    if action.kind == "opportunity_attack":
        roll_die = state.dice.roll_die
        roll_dice = state.dice.roll_dice
        request = opportunity_attack_request(decision)
        movement = request.movement
        eligibility = state.combat_rules.reaction_eligibility(
            state,
            reactor_ref,
            "opportunity_attack",
        )
        if not eligibility.allowed:
            raise ValueError(eligibility.failures[0].message)
        reactor.reaction_available = False
        target_ref = movement.creature_ref
        target = state.creatures[target_ref]
        target_label = creature_label(state, target_ref)
        reactor_label = creature_label(state, reactor_ref)
        attack_roll_rules = state.combat_rules.roll_modifiers(
            state,
            reactor_ref,
            "attack_roll",
        )
        damage_roll_rules = state.combat_rules.roll_modifiers(
            state,
            reactor_ref,
            "damage_roll",
        )
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
            attack_roll_mode_override=attack_roll_mode_for(
                state,
                reactor_ref,
                target_ref,
                "melee",
                reactor.position,
                (target.position,),
            ),
            sourced_attack_modifier=attack_roll_rules.resolve_modifier(roll_die),
            sourced_attack_roll_mode=attack_roll_rules.mode,
            target_armor_class=state.combat_rules.effective_armor_class(
                state,
                target_ref,
            ).value,
            sourced_damage_modifier_for=lambda: damage_roll_rules.resolve_modifier(
                roll_die
            ),
            d20_roller=roll_die,
            dice_roller=roll_dice,
            automatic_critical_provider_ids=(
                automatic_critical_provider_ids_for(
                    state,
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
            create_event(
                state,
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
                create_event(
                    state,
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
