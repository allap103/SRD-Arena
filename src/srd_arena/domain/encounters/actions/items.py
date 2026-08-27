"""Provide items support for the actions package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ..models import EncounterProgress
from .consumables import healing_potion_dice

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_dice(count: int, sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def resolve_utilize_action(
    self: EncounterState,
    actor: Creature,
    item_id: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve utilize action."""

    creature_ref = self.current_decision().creature_ref
    item = self.item_templates.get(item_id)
    if item is None or not actor.inventory.has_item(item_id):
        progress.messages.append(("system", "You do not have that item."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "utilize", "item_id": item_id, "success": False},
            )
        )
        return
    if not self.active_bonus_action_available:
        progress.messages.append(("system", "You have already used your Bonus Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={
                    "kind": "utilize",
                    "item_id": item.id,
                    "item_name": item.name,
                    "success": False,
                },
            )
        )
        return
    healing_dice = healing_potion_dice(item)
    if healing_dice is None:
        progress.messages.append(
            ("system", f"{item.name} cannot be used that way yet.")
        )
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={
                    "kind": "utilize",
                    "item_id": item.id,
                    "item_name": item.name,
                    "success": False,
                },
            )
        )
        return

    dice_count, dice_sides, modifier = healing_dice
    dice_total = _roll_dice(dice_count, dice_sides)
    healing_total = dice_total + modifier
    applied_healing = actor.heal(healing_total)
    consumed = item.has_misc_tag("CNS")
    if consumed:
        actor.inventory.remove_item(item.id)
    self.active_bonus_action_available = False

    modifier_text = f" + {modifier}" if modifier else ""
    progress.messages.extend(
        [
            ("system", f"{actor.name} drinks {item.name}."),
            (
                "system",
                f"Healing: {dice_count}d{dice_sides}={dice_total}{modifier_text} "
                f"= {healing_total}; applied {applied_healing}.",
            ),
        ]
    )
    if consumed:
        progress.messages.append(("system", f"{item.name} is consumed."))
    progress.events.append(
        self._event(
            "item_used",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "utilize",
                "mode": "drink",
                "item_id": item.id,
                "item_name": item.name,
                "target_ref": creature_ref,
                "target_label": actor.name,
                "success": True,
                "consumed": consumed,
                "effect": "healing",
                "healing": applied_healing,
                "healing_roll_detail": {
                    "dice": f"{dice_count}d{dice_sides}",
                    "dice_total": dice_total,
                    "modifier": modifier,
                    "total": healing_total,
                    "applied_healing": applied_healing,
                },
            },
        )
    )
