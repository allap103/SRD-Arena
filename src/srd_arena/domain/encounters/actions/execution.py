"""Route accepted encounter actions into the matching execution pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature, can_grapple
from srd_arena.domain.effects.application import condition_from_effect_with_origin
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.rolls.dice import resolve_d20

from ..attack_economy import spend_attack
from ..behaviors import is_adjacent as _is_adjacent
from ..encounter_models.actions import EncounterAction
from ..encounter_models.resolution import EncounterProgress
from ..grappling_state import apply_grapple
from ..rule_queries.rolls import roll_modifiers
from ..state_runtime import create_event, creature_label
from .attack_resolution import has_free_hand
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
    """Route a grapple or escape action through its contested-check resolver.

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

    actor_roll_rules = roll_modifiers(
        state,
        creature_ref,
        "ability_check",
        ability="strength",
    )
    target_roll_rules = roll_modifiers(
        state,
        target_ref,
        "ability_check",
        ability="strength",
    )
    roll_die = state.dice.roll_die
    actor_roll = resolve_d20(
        modifier=(
            actor.get_modifier(actor.attributes.strength)
            + actor_roll_rules.resolve_modifier(roll_die)
        ),
        mode=actor_roll_rules.mode,
        roller=roll_die,
    )
    target_roll = resolve_d20(
        modifier=(
            target.creature.get_modifier(target.creature.attributes.strength)
            + target_roll_rules.resolve_modifier(roll_die)
        ),
        mode=target_roll_rules.mode,
        roller=roll_die,
    )
    success = actor_roll.total >= target_roll.total
    target_label = creature_label(state, target_ref)

    progress.events.append(
        create_event(
            state,
            "grapple_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "target_ref": target_ref,
                "target_label": target_label,
                "actor_roll": actor_roll.total,
                "target_roll": target_roll.total,
                "actor_die": actor_roll.selected,
                "target_die": target_roll.selected,
                "success": success,
            },
        )
    )

    if not success:
        progress.messages.append(
            ("system", f"{actor.name} fails to grapple {target_label}.")
        )
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return

    progress.messages.append(("system", f"{actor.name} grapples {target_label}."))
    progress.messages.append(("system", f"{target_label} is grappled."))
    apply_grapple(
        state,
        condition_from_effect_with_origin(
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": creature_ref,
                    "source_label": actor.name,
                    "source_kind": "action",
                    "definition_id": "grapple",
                },
            ),
            origin_id=action_id,
        ),
    )
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={"kind": "grapple", "success": True, "target_ref": target_ref},
        )
    )
