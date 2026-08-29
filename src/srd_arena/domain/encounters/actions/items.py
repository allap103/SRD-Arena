"""Execute encounter actions granted by inventory items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.rolls.dice import resolve_dice

from ..encounter_models.resolution import EncounterProgress
from ..rule_queries.health import apply_healing
from ..state_runtime import create_event
from .consumables import healing_potion_dice
from .rejections import reject_action

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_utilize_action(
    state: EncounterState,
    actor: Creature,
    item_id: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Consume a supported inventory item and apply its action outcome.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(
    ...     inventory=SimpleNamespace(has_item=lambda item_id: False)
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="hero"),
    ...     item_templates={}, event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_utilize_action(state, actor, "potion", progress, "use-1")
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'You do not have that item.'), 'item_unavailable')
    """

    creature_ref = state.current_decision().creature_ref
    item = state.item_templates.get(item_id)
    if item is None or not actor.inventory.has_item(item_id):
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="utilize",
            message="You do not have that item.",
            reason_code="item_unavailable",
            details={"item_id": item_id},
        )
        return
    if not state.active_bonus_action_available:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="utilize",
            message="You have already used your Bonus Action.",
            reason_code="bonus_action_spent",
            details={"item_id": item.id, "item_name": item.name},
        )
        return
    healing_dice = healing_potion_dice(item)
    if healing_dice is None:
        reject_action(
            state,
            progress,
            actor_ref=creature_ref,
            action_id=action_id,
            action_kind="utilize",
            message=f"{item.name} cannot be used that way yet.",
            reason_code="item_unimplemented",
            details={"item_id": item.id, "item_name": item.name},
        )
        return

    dice_count, dice_sides, modifier = healing_dice
    roll = resolve_dice(
        dice_count,
        dice_sides,
        modifier=modifier,
        roller=state.dice.roll_die,
    )
    dice_total = roll.subtotal
    healing_total = roll.total
    applied_healing = apply_healing(
        state,
        creature_ref,
        healing_total,
    )
    consumed = item.has_misc_tag("CNS")
    if consumed:
        actor.inventory.remove_item(item.id)
    state.active_bonus_action_available = False

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
        create_event(
            state,
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
                    "dice_values": [die.result for die in roll.dice],
                    "die_rolls": [list(die.rolls) for die in roll.dice],
                    "dice_total": dice_total,
                    "modifier": modifier,
                    "total": healing_total,
                    "applied_healing": applied_healing,
                },
            },
        )
    )
