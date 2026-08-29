"""Resolve Grapple and escape actions together with their source relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.rolls.dice import resolve_d20

from ..attack_economy import consume_action
from ..condition_state import remove_condition_from_source
from ..encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from ..encounter_models.resolution import EncounterProgress
from ..rule_queries.rolls import roll_modifiers
from ..state_runtime import create_event
from .rejections import reject_action

if TYPE_CHECKING:
    from ..encounter import EncounterState


def available_escape_actions(
    state: EncounterState,
    creature_ref: str,
) -> list[EncounterAction]:
    """Advertise one escape choice for each creature currently grappling the actor.

    >>> from types import SimpleNamespace
    >>> applied = SimpleNamespace(
    ...     condition=Condition.GRAPPLED,
    ...     metadata={"escape_dc": 13},
    ...     source_ref="ogre",
    ...     source_label="Ogre",
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(actions_remaining=1)},
    ...     conditions_for=lambda ref: (applied,),
    ... )
    >>> action = available_escape_actions(state, "hero")[0]
    >>> (action.kind, action.value, action.cost.action)
    ('escape_grapple', 'ogre', 1)
    """

    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0:
        return []
    actions = []
    for applied in state.conditions_for(creature_ref):
        escape_dc = applied.metadata.get("escape_dc")
        source_ref = applied.source_ref
        if (
            applied.condition is not Condition.GRAPPLED
            or not isinstance(escape_dc, int)
            or source_ref is None
        ):
            continue
        actions.append(
            EncounterAction(
                f"Escape {applied.source_label} (DC {escape_dc})",
                "escape_grapple",
                source_ref,
                id=(f"{creature_ref}-escape-grapple-{source_ref.replace(':', '-')}"),
                creature_ref=creature_ref,
                cost=ActionCost(action=1),
            )
        )
    return actions


def resolve_escape_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve an escape contest and remove only the selected grapple source on success.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="hero"),
    ...     creatures={"hero": SimpleNamespace(actions_remaining=0)},
    ...     event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_escape_action(
    ...     state, SimpleNamespace(), EncounterAction("Escape", "escape_grapple"),
    ...     progress, "escape-1"
    ... )
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'No Action remains to escape a grapple.'), 'action_spent')
    """

    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="escape_grapple",
            message="No Action remains to escape a grapple.",
            reason_code="action_spent",
        )
        return
    if not isinstance(action.value, str):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="escape_grapple",
            message="Escape grapple requires the grappler reference.",
            reason_code="source_required",
        )
        return
    grapple = next(
        (
            applied
            for applied in state.conditions_for(creature_ref)
            if applied.condition is Condition.GRAPPLED
            and applied.source_ref == action.value
            and isinstance(applied.metadata.get("escape_dc"), int)
        ),
        None,
    )
    if grapple is None:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="escape_grapple",
            message="That grapple is no longer active.",
            reason_code="grapple_unavailable",
            details={"source_ref": action.value},
        )
        return
    consume_action(state, allow_magic=False)
    escape_dc = grapple.metadata["escape_dc"]
    if not isinstance(escape_dc, int):
        raise RuntimeError("Grapple escape DC must be an integer.")
    strength_modifier = creature.get_modifier(creature.attributes.strength)
    dexterity_modifier = creature.get_modifier(creature.attributes.dexterity)
    ability = "strength" if strength_modifier >= dexterity_modifier else "dexterity"
    modifier = max(strength_modifier, dexterity_modifier)
    roll_rules = roll_modifiers(
        state,
        creature_ref,
        "ability_check",
        ability=ability,
    )
    roll_die = state.dice.roll_die
    check = resolve_d20(
        modifier=modifier + roll_rules.resolve_modifier(roll_die),
        mode=roll_rules.mode,
        roller=roll_die,
    )
    success = check.total >= escape_dc
    if success:
        remove_condition_from_source(
            state,
            creature_ref,
            Condition.GRAPPLED,
            action.value,
        )
    progress.messages.append(
        (
            "system",
            f"{creature.name} {'escapes' if success else 'fails to escape'} "
            f"{grapple.source_label}'s grapple "
            f"(rolled {check.total} vs DC {escape_dc}).",
        )
    )
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "escape_grapple",
                "source_ref": action.value,
                "dc": escape_dc,
                "roll": check.total,
                "success": success,
            },
        )
    )
