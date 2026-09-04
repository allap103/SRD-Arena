"""Offer and resolve Alert's optional post-roll Initiative swap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures.feature_rules import (
    can_use_alert_initiative_swap,
)
from srd_arena.domain.effects.conditions import Condition

from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import DecisionFrame, InitiativeSwapRequest
from ..encounter_models.resolution import DecisionExecutionResult, EncounterProgress
from ..participants import (
    creature_controller,
    creature_team_id,
)
from ..state_runtime import create_event, creature_label

if TYPE_CHECKING:
    from ..encounter import EncounterState


def initialize_initiative_swap_decisions(state: EncounterState) -> None:
    """Queue Alert choices for externally controlled creatures before turn one.

    Scripted Alert users exercise the valid default of keeping their rolled
    Initiative. Allied scripted creatures are considered willing recipients
    when their external teammate requests a swap.
    """

    if not state.initiative_entries:
        return

    owners = [
        creature_ref
        for creature_ref in state.initiative_order
        if creature_controller(state, creature_ref) == "external"
        and can_use_alert_initiative_swap(state.creatures[creature_ref].creature)
        and eligible_initiative_swap_allies(state, creature_ref)
    ]
    for creature_ref in reversed(owners):
        state.interrupts.decision_stack.append(
            DecisionFrame(
                id=f"initiative-swap-{creature_ref.replace(':', '-')}",
                creature_ref=creature_ref,
                kind="initiative_swap",
                reason="alert_initiative_swap",
                request=InitiativeSwapRequest(creature_ref),
            )
        )


def initiative_swap_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer keeping Initiative or swapping it with each eligible ally."""

    decision = state.current_decision()
    request = _initiative_swap_request(decision)
    actions = [
        EncounterAction(
            "Keep current initiative",
            "keep_initiative",
            id=f"{decision.id}-keep",
            creature_ref=request.owner_ref,
        )
    ]
    actions.extend(
        EncounterAction(
            f"Swap initiative with {creature_label(state, ally_ref)}",
            "swap_initiative",
            ally_ref,
            id=f"{decision.id}-with-{ally_ref.replace(':', '-')}",
            creature_ref=request.owner_ref,
        )
        for ally_ref in eligible_initiative_swap_allies(state, request.owner_ref)
    )
    return actions


def apply_initiative_swap_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Apply one advertised Alert choice and complete its decision frame."""

    request = _initiative_swap_request(decision)
    progress = EncounterProgress()
    if action.kind == "keep_initiative" and action.value is None:
        target_ref = None
    elif action.kind == "swap_initiative" and isinstance(action.value, str):
        target_ref = action.value
        if target_ref not in eligible_initiative_swap_allies(
            state,
            request.owner_ref,
        ):
            raise ValueError(
                "The selected ally is no longer eligible to swap Initiative."
            )
        _swap_initiative(state, request.owner_ref, target_ref)
        progress.messages.append(
            (
                "system",
                f"{creature_label(state, request.owner_ref)} swaps initiative "
                f"with {creature_label(state, target_ref)}.",
            )
        )
    else:
        raise ValueError("Alert requires keeping Initiative or selecting an ally.")

    progress.events.append(
        create_event(
            state,
            "initiative_swap_resolved",
            creature_ref=request.owner_ref,
            frame_id=decision.id,
            action_id=action.id,
            data={
                "feature_id": "alert",
                "target_ref": target_ref,
                "swapped": target_ref is not None,
                "initiative_order": list(state.initiative_order),
            },
        )
    )
    return DecisionExecutionResult(progress, action.id, completed=True)


def eligible_initiative_swap_allies(
    state: EncounterState,
    owner_ref: str,
) -> tuple[str, ...]:
    """Return willing allies that can currently participate in Alert's swap."""

    if not state.creatures[owner_ref].is_alive or state.has_condition(
        owner_ref, Condition.INCAPACITATED
    ):
        return ()
    owner_team = creature_team_id(state, owner_ref)
    turn_participants = {
        participant.creature_id
        for participant in state.definition.participants
        if participant.takes_turns
    }
    return tuple(
        candidate_ref
        for candidate_ref in state.initiative_order
        if candidate_ref != owner_ref
        and state.creatures[candidate_ref].creature_id in turn_participants
        and state.creatures[candidate_ref].is_alive
        and creature_team_id(state, candidate_ref) == owner_team
        and not state.has_condition(candidate_ref, Condition.INCAPACITATED)
    )


def _initiative_swap_request(decision: DecisionFrame) -> InitiativeSwapRequest:
    """Return the typed Alert request carried by a decision frame."""

    if not isinstance(decision.request, InitiativeSwapRequest):
        raise TypeError("Initiative swap decision requires an Alert request.")
    return decision.request


def _swap_initiative(
    state: EncounterState,
    owner_ref: str,
    target_ref: str,
) -> None:
    """Exchange effective Initiative totals and restore deterministic order."""

    owner = next(
        entry for entry in state.initiative_entries if entry.creature_ref == owner_ref
    )
    target = next(
        entry for entry in state.initiative_entries if entry.creature_ref == target_ref
    )
    owner.total, target.total = target.total, owner.total
    state.initiative_entries.sort(
        key=lambda entry: (
            -entry.total,
            -entry.modifier,
            entry.creature_ref,
        )
    )
    state.initiative_order = [entry.creature_ref for entry in state.initiative_entries]
