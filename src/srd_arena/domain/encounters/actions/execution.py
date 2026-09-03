"""Route accepted encounter actions into the matching execution pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature, can_grapple

from ..attack_economy import spend_attack
from ..behaviors import is_adjacent as _is_adjacent
from ..encounter_models.actions import EncounterAction
from ..encounter_models.decisions import DecisionFrame, GrappleSaveRequest
from ..encounter_models.resolution import EncounterProgress
from ..participants import creature_controller
from ..state_runtime import create_event, next_frame_id
from .attack_resolution import has_free_hand
from .grapple_saves import preferred_grapple_save_ability, resolve_grapple_save
from .rejections import reject_action

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_grapple_action(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Start a target-chosen saving throw against one Grapple attempt.

    >>> from types import SimpleNamespace
    >>> creature_state = SimpleNamespace(actions_remaining=0, attacks_remaining=0)
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="hero"),
    ...     creatures={"hero": creature_state}, event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_grapple_action(
    ...     state, SimpleNamespace(), EncounterAction("Grapple", "grapple"),
    ...     progress, "grapple-1"
    ... )
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'You have already used your Action.'), 'action_spent')
    """

    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0 and creature_state.attacks_remaining <= 0:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="You have already used your Action.",
            reason_code="action_spent",
        )
        return
    if not isinstance(action.value, str):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="A creature target is required.",
            reason_code="target_required",
        )
        return

    target_ref = action.value
    target = state.creatures.get(target_ref)
    if target is None or not target.is_alive:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="The target is no longer available.",
            reason_code="target_unavailable",
            details={"target_ref": target_ref},
        )
        return
    if not _is_adjacent(creature_state.position, target.position):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="The target is out of reach.",
            reason_code="target_out_of_range",
            details={"target_ref": target_ref},
        )
        return
    if not has_free_hand(actor):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="You need a free hand to grapple.",
            reason_code="free_hand_required",
            details={"target_ref": target_ref},
        )
        return
    if not can_grapple(target.creature.size, actor.size):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="grapple",
            message="The target is too large to grapple.",
            reason_code="target_too_large",
            details={"target_ref": target_ref},
        )
        return

    spend_attack(
        state,
        creature_ref,
        base_attacks=actor.combat_profile.attacks_per_attack_action,
    )
    save_dc = (
        8
        + actor.get_modifier(actor.attributes.strength)
        + actor.attributes.proficiency_bonus
    )
    request = GrappleSaveRequest(
        action_id=action_id,
        grappler_ref=creature_ref,
        target_ref=target_ref,
        save_dc=save_dc,
    )
    if creature_controller(state, target_ref) == "scripted":
        resolve_grapple_save(
            state,
            request,
            preferred_grapple_save_ability(target.creature),
            progress,
        )
        return

    frame_id = next_frame_id(state, prefix="grapple_save")
    current_frame = state.current_decision()
    state.interrupts.decision_stack.append(
        DecisionFrame(
            id=frame_id,
            creature_ref=target_ref,
            kind="grapple_save",
            reason="grapple_attempt",
            parent_frame_id=current_frame.id,
            parent_action_id=action_id,
            request=request,
        )
    )
    progress.paused_for_decision = True
    progress.events.append(
        create_event(
            state,
            "decision_opened",
            creature_ref=target_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={
                "kind": "grapple_save",
                "grappler_ref": creature_ref,
                "target_ref": target_ref,
                "save_dc": save_dc,
            },
        )
    )
