"""Resolve Grapple and escape actions together with their source relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...effects.conditions import Condition
from ...rolls.dice import resolve_d20
from ..attack_economy import consume_action
from ..condition_state import remove_condition_from_source
from ..encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from ..encounter_models.resolution import EncounterProgress
from ..state_runtime import create_event

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


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
    ... )
    >>> resolve_escape_action(
    ...     state, SimpleNamespace(), EncounterAction("Escape", "escape_grapple"),
    ...     EncounterProgress(), "escape-1"
    ... )
    Traceback (most recent call last):
    ...
    RuntimeError: No Action remains to escape a grapple.
    """

    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0:
        raise RuntimeError("No Action remains to escape a grapple.")
    if not isinstance(action.value, str):
        raise ValueError("Escape grapple requires the grappler reference.")
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
        raise RuntimeError("That grapple is no longer active.")
    consume_action(state, allow_magic=False)
    escape_dc = grapple.metadata["escape_dc"]
    if not isinstance(escape_dc, int):
        raise RuntimeError("Grapple escape DC must be an integer.")
    strength_modifier = creature.get_modifier(creature.attributes.strength)
    dexterity_modifier = creature.get_modifier(creature.attributes.dexterity)
    ability = "strength" if strength_modifier >= dexterity_modifier else "dexterity"
    modifier = max(strength_modifier, dexterity_modifier)
    roll_rules = state.combat_rules.roll_modifiers(
        state,
        creature_ref,
        "ability_check",
        ability=ability,
    )
    check = resolve_d20(
        modifier=modifier + roll_rules.resolve_modifier(_roll_die),
        mode=roll_rules.mode,
        roller=_roll_die,
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
