from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...effects.conditions import Condition
from ...rolls.dice import resolve_d20
from ..models import ActionCost, EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def available_escape_actions(
    state: EncounterState,
    creature_ref: str,
) -> list[EncounterAction]:
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
    state._consume_action(allow_magic=False)
    escape_dc = grapple.metadata["escape_dc"]
    if not isinstance(escape_dc, int):
        raise RuntimeError("Grapple escape DC must be an integer.")
    strength_modifier = creature.get_modifier(creature.attributes.strength)
    dexterity_modifier = creature.get_modifier(creature.attributes.dexterity)
    ability = "strength" if strength_modifier >= dexterity_modifier else "dexterity"
    modifier = max(strength_modifier, dexterity_modifier)
    check = resolve_d20(
        modifier=modifier
        + creature.resolve_roll_modifiers("ability_check", _roll_die, ability),
        mode=creature.roll_mode("ability_check", ability),
        roller=_roll_die,
    )
    success = check.total >= escape_dc
    if success:
        state._remove_condition_from_source(
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
        state._event(
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
