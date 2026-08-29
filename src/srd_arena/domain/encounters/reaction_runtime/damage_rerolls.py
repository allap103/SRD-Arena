"""Offer, mutate, and finalize optional damage-die reroll decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.triggered import TriggeredEffect, reroll_eligible_indices
from srd_arena.domain.rolls.dice import reroll_dice

from ..actions.attack_resolution import apply_attack_damage, damage_roll_detail
from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import (
    DecisionContinuation,
    DecisionFrame,
)
from ..encounter_models.resolution import (
    AttackOutcome,
    DamageRerollRequest,
    DecisionExecutionResult,
    EncounterProgress,
)
from ..refs import reroll_die_action_id as _reroll_die_action_id
from ..rule_queries.defenses import apply_damage
from ..state_runtime import create_event, next_frame_id
from .attack_lifecycle import resolve_attack_lifecycle

if TYPE_CHECKING:
    from ..encounter import EncounterState


def damage_reroll_request(decision: DecisionFrame) -> DamageRerollRequest:
    """Read and type-check the request owned by a reroll decision frame.

    >>> from unittest.mock import Mock
    >>> request = Mock(spec=DamageRerollRequest)
    >>> frame = DecisionFrame("reroll", "hero", "reroll_dice", "feature")
    >>> frame.request = request
    >>> damage_reroll_request(frame) is request
    True
    """

    if not isinstance(decision.request, DamageRerollRequest):
        raise RuntimeError(
            f"Decision '{decision.id}' does not contain a damage reroll request."
        )
    return decision.request


def open_damage_reroll_decision(
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
    """Push one damage-reroll frame above its exact parent invocation.

    >>> from types import SimpleNamespace
    >>> attack = AttackOutcome([("system", "Hit")], True, 18, 4, False, {})
    >>> effect = TriggeredEffect(
    ...     "great_weapon_fighting", "feature", "gwm", "damage_roll",
    ...     "reroll_matching_dice", parameters={"values": [1, 2]},
    ... )
    >>> parent = DecisionFrame("turn-1", "hero", "turn", "active")
    >>> state = SimpleNamespace(
    ...     frame_sequence=1, event_sequence=1,
    ...     current_decision=lambda: parent,
    ...     active_attacks_remaining=0,
    ...     interrupts=SimpleNamespace(decision_stack=[]),
    ... )
    >>> progress = EncounterProgress()
    >>> open_damage_reroll_decision(
    ...     state, attack=attack, triggered_effect=effect,
    ...     attacker_ref="hero", target_ref="goblin",
    ...     attacker_label="Hero", target_label="Goblin",
    ...     action_id="attack-1", progress=progress,
    ... )
    >>> (state.interrupts.decision_stack[-1].kind, progress.paused_for_decision, attack.messages)
    ('reroll_dice', True, [])
    """

    frame_id = next_frame_id(state)
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
    state.interrupts.decision_stack.append(
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
            f"{triggered_effect.id.replace('_', ' ').title()} can reroll "
            "qualifying damage dice.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "attack_pending",
            creature_ref=attacker_ref,
            frame_id=frame_id,
            action_id=action_id,
            data=damage_reroll_event_data(request),
        )
    )
    progress.paused_for_decision = True


def reroll_damage_actions(state: EncounterState) -> list[EncounterAction]:
    """Build the choices for the active damage-reroll frame.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.rolls.dice import DicePoolResult, DieRollResult
    >>> attack = AttackOutcome(
    ...     [], True, 18, 6, False, {},
    ...     damage_roll=DicePoolResult((DieRollResult(6, (1,)),), 0, 1, 1),
    ...     damage_dice="1d6",
    ... )
    >>> effect = TriggeredEffect(
    ...     "gwm", "feature", "gwm", "damage_roll", "reroll_matching_dice",
    ...     parameters={"values": [1, 2]},
    ... )
    >>> request = DamageRerollRequest(
    ...     "attack-1", "hero", "goblin", "Hero", "Goblin", 0,
    ...     attack, effect,
    ... )
    >>> frame = DecisionFrame(
    ...     "reroll", "hero", "reroll_dice", "gwm", request=request
    ... )
    >>> actions = reroll_damage_actions(
    ...     SimpleNamespace(current_decision=lambda: frame)
    ... )
    >>> [(action.kind, action.value) for action in actions]
    [('reroll_die', 0), ('accept_roll', None)]
    """

    request = damage_reroll_request(state.current_decision())
    if request.attack.damage_roll is None:
        return []
    actions = [
        EncounterAction(
            f"Reroll damage die {index + 1} "
            f"({request.attack.damage_roll.dice[index].result})",
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
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Apply one reroll/accept choice without closing its decision frame.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.effects.triggered import TriggeredEffect
    >>> from srd_arena.domain.rolls.dice import DicePoolResult, DieRollResult
    >>> attack = AttackOutcome(
    ...     [], True, 18, 5, False, {},
    ...     damage_roll=DicePoolResult((DieRollResult(6, (5,)),), 0, 5, 5),
    ... )
    >>> request = DamageRerollRequest(
    ...     "attack-1", "hero", "goblin", "Hero", "Goblin", 0, attack,
    ...     TriggeredEffect("gwm", "feature", "gwm", "damage_roll", "reroll_matching_dice"),
    ... )
    >>> frame = DecisionFrame(
    ...     "reroll", "hero", "reroll_dice", "gwm", request=request
    ... )
    >>> state = SimpleNamespace(event_sequence=1)
    >>> with patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.damage_rerolls."
    ...     "finalize_damage_reroll"
    ... ) as finalize:
    ...     result = apply_damage_reroll_action(
    ...         state, EncounterAction("Accept", "accept_roll"), frame
    ...     )
    >>> (result.completed, finalize.call_count)
    (True, 1)
    """

    request = damage_reroll_request(decision)
    if request.attack.damage_roll is None:
        raise RuntimeError("Damage reroll requested without a pending attack.")
    progress = EncounterProgress()
    progress.events.append(
        create_event(
            state,
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
            roller=state.dice.roll_die,
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
            create_event(
                state,
                "damage_rerolled",
                creature_ref=request.attacker_ref,
                frame_id=decision.id,
                action_id=request.action_id,
                data=damage_reroll_event_data(request),
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

    finalize_damage_reroll(state, request, progress, decision)
    return DecisionExecutionResult(
        progress=progress,
        action_id=request.action_id,
        completed=True,
    )


def finalize_damage_reroll(
    state: EncounterState,
    request: DamageRerollRequest,
    progress: EncounterProgress,
    decision: DecisionFrame,
) -> None:
    """Apply accepted damage and record the completed attack.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> attack = AttackOutcome([], True, 18, 5, False, {})
    >>> effect = TriggeredEffect(
    ...     "gwm", "feature", "gwm", "damage_roll", "reroll_matching_dice"
    ... )
    >>> request = DamageRerollRequest(
    ...     "attack-1", "hero", "goblin", "Hero", "Goblin", 0,
    ...     attack, effect,
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={
    ...         "hero": SimpleNamespace(creature=SimpleNamespace(name="Hero")),
    ...         "goblin": SimpleNamespace(creature=object(), is_alive=True),
    ...     }, event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> frame = DecisionFrame("reroll", "hero", "reroll_dice", "gwm")
    >>> with patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.damage_rerolls."
    ...     "apply_attack_damage"
    ... ), patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.damage_rerolls."
    ...     "resolve_attack_lifecycle"
    ... ):
    ...     finalize_damage_reroll(state, request, progress, frame)
    >>> [event.type for event in progress.events]
    ['attack_resolved']
    """

    attacker = state.creatures[request.attacker_ref].creature
    target = state.creatures[request.target_ref]
    apply_attack_damage(
        request.attack,
        target.creature,
        attacker_label=attacker.name,
        target_label=request.target_label,
        damage_receiver=lambda amount, damage_type: apply_damage(
            state,
            request.target_ref,
            amount,
            damage_type,
        ),
    )
    resolve_attack_lifecycle(
        state,
        attacker_ref=request.attacker_ref,
        target_ref=request.target_ref,
        damage=request.attack.damage,
        progress=progress,
    )
    progress.messages.extend(request.attack.messages)
    progress.events.append(
        create_event(
            state,
            "attack_resolved",
            creature_ref=request.attacker_ref,
            frame_id=decision.id,
            action_id=request.action_id,
            data={
                **damage_reroll_event_data(request),
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
            create_event(
                state,
                "creature_defeated",
                creature_ref=request.target_ref,
                frame_id=decision.id,
                action_id=request.action_id,
            )
        )


def damage_reroll_event_data(
    request: DamageRerollRequest,
) -> dict[str, object]:
    """Serialize the pending reroll choices into combat-event data.

    >>> from srd_arena.domain.effects.triggered import TriggeredEffect
    >>> from srd_arena.domain.rolls.dice import DicePoolResult, DieRollResult
    >>> attack = AttackOutcome(
    ...     [], True, 18, 6, False, {"total": 18},
    ...     damage_roll=DicePoolResult(
    ...         (DieRollResult(6, (1,)), DieRollResult(6, (5,))), 0, 6, 6
    ...     ),
    ...     damage_dice="2d6",
    ... )
    >>> effect = TriggeredEffect(
    ...     "great_weapon_fighting", "feature", "gwm", "damage_roll",
    ...     "reroll_matching_dice", parameters={"values": [1, 2]},
    ... )
    >>> request = DamageRerollRequest(
    ...     "attack-1", "hero", "target", "Hero", "Target", 0,
    ...     attack, effect,
    ... )
    >>> data = damage_reroll_event_data(request)
    >>> (data["eligible_die_indices"], data["accept_action_id"])
    ([0], 'attack-1-accept-damage')
    """

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
