"""Provide special support for the creature actions package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...behaviors import is_adjacent as _is_adjacent
from ...models import ActionCost, CreatureRef, EncounterAction
from ..consumables import healing_potions_in_inventory
from ..grappling import available_escape_actions

if TYPE_CHECKING:
    from ...encounter import EncounterState


def special_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Handle special action candidates."""

    actor = state.creatures[creature_ref]
    actions: list[EncounterAction] = []
    actions.extend(state._available_feature_actions(actor.creature))
    actions.extend(state._available_spell_actions(actor.creature))

    for effect in state.ongoing_effects:
        end_events = effect.parameters.get("end_events", [])
        if (
            not isinstance(end_events, list)
            or [
                "adjacent_creature_wakes_target",
                "any",
            ]
            not in end_events
        ):
            continue
        for target_ref in effect.target_refs:
            wake_target_state = state.creatures.get(target_ref)
            if (
                wake_target_state is None
                or not wake_target_state.is_alive
                or target_ref == creature_ref
            ):
                continue
            if not _is_adjacent(actor.position, wake_target_state.position):
                continue
            actions.append(
                EncounterAction(
                    f"Wake {wake_target_state.creature.name}",
                    "wake_spell_target",
                    target_ref,
                    id=f"{creature_ref}-wake-{target_ref.replace(':', '-')}",
                    creature_ref=creature_ref,
                    cost=ActionCost(action=1),
                )
            )

    actions.extend(available_escape_actions(state, creature_ref))
    for item in healing_potions_in_inventory(
        actor.creature,
        state.item_templates,
    ):
        actions.append(
            EncounterAction(
                f"Drink {item.name}",
                "utilize",
                item.id,
                id=f"{creature_ref}-utilize-drink-{item.id}",
                creature_ref=creature_ref,
                cost=ActionCost(bonus_action=1),
            )
        )
    actions.append(
        EncounterAction(
            "Wait",
            "wait",
            id=f"{creature_ref}-wait",
            creature_ref=creature_ref,
        )
    )
    return actions
