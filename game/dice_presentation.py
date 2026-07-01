from __future__ import annotations

from dataclasses import dataclass
import re

from .encounter import CombatEvent


@dataclass(frozen=True)
class DieView:
    expression: str
    value: int
    selected: bool = True
    history: tuple[int, ...] = ()
    action_id: str | None = None


@dataclass(frozen=True)
class RollView:
    label: str
    dice: tuple[DieView, ...]
    modifier: int
    total: int
    target: int | None = None
    success: bool | None = None
    roll_id: str | None = None


def build_roll_views(events: list[CombatEvent]) -> list[RollView]:
    views: list[RollView] = []
    resolved_roll_ids = {
        event.data.get("roll_id")
        for event in events
        if event.type == "attack_resolved" and isinstance(event.data.get("roll_id"), str)
    }
    for event in events:
        if event.type in {"attack_resolved", "attack_pending"}:
            if event.type == "attack_pending" or not isinstance(
                event.data.get("roll_id"),
                str,
            ):
                attack = _attack_roll_view(event)
                if attack is not None:
                    views.append(attack)
            damage = _pool_roll_view(
                event.data.get("damage_roll_detail"),
                label="Damage",
                roll_id=event.data.get("roll_id"),
                reroll_action_ids=event.data.get("reroll_action_ids"),
            )
            if damage is not None:
                views.append(damage)
            continue

        if event.type == "damage_rerolled":
            if event.data.get("roll_id") in resolved_roll_ids:
                continue
            damage = _pool_roll_view(
                event.data.get("damage_roll_detail"),
                label="Damage reroll",
                roll_id=event.data.get("roll_id"),
                reroll_action_ids=event.data.get("reroll_action_ids"),
            )
            if damage is not None:
                views.append(damage)
            continue

        if event.type in {"action_resolved", "feature_used"}:
            healing = _pool_roll_view(
                event.data.get("healing_roll_detail"),
                label="Healing",
            )
            if healing is not None:
                views.append(healing)
            continue

        if event.type == "spell_cast":
            views.extend(_saving_throw_roll_views(event))
            views.extend(_spell_damage_roll_views(event))
    return views


def without_roll_details(
    messages: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Remove prose formulas represented by the structured roll log."""
    return [
        (channel, message)
        for channel, message in messages
        if not (
            "Roll d20=" in message
            or message.startswith("Damage to ")
            or message.startswith("Healing:")
            or " save: d20=" in message
        )
    ]


def _attack_roll_view(event: CombatEvent) -> RollView | None:
    detail = event.data.get("attack_roll_detail")
    if not isinstance(detail, dict):
        return None
    die = detail.get("die")
    dice = detail.get("dice")
    selected_index = detail.get("selected_index")
    modifier = detail.get("modifier")
    total = detail.get("total")
    target = detail.get("target_ac")
    if not all(isinstance(value, int) for value in (die, modifier, total)):
        return None
    attacker = event.data.get("attacker_label")
    target_label = event.data.get("target_label")
    label = "Attack"
    if isinstance(attacker, str) and isinstance(target_label, str):
        label = f"{attacker} attacks {target_label}"
    rendered_dice = _attack_dice_views(
        die=die,
        dice=dice,
        selected_index=selected_index,
    )
    return RollView(
        label=label,
        dice=rendered_dice,
        modifier=modifier,
        total=total,
        target=target if isinstance(target, int) else None,
        success=event.data.get("hit") if isinstance(event.data.get("hit"), bool) else None,
    )


def _saving_throw_roll_views(event: CombatEvent) -> list[RollView]:
    details = event.data.get("save_details")
    if not isinstance(details, list):
        detail = event.data.get("save_detail")
        details = [detail] if isinstance(detail, dict) else []
    views: list[RollView] = []
    spell_name = event.data.get("spell_name")
    for detail in details:
        if not isinstance(detail, dict):
            continue
        roll_view = _saving_throw_roll_view(detail, spell_name)
        if roll_view is not None:
            views.append(roll_view)
    return views


def _saving_throw_roll_view(
    detail: dict[str, object],
    spell_name: object,
) -> RollView | None:
    die = detail.get("die")
    dice = detail.get("dice")
    selected_index = detail.get("selected_index")
    modifier = detail.get("modifier")
    total = detail.get("total")
    target = detail.get("target_dc")
    success = detail.get("success")
    target_label = detail.get("target_label")
    ability = detail.get("ability")
    if not all(isinstance(value, int) for value in (die, modifier, total)):
        return None
    label = "Saving Throw"
    if isinstance(target_label, str) and isinstance(ability, str):
        label = f"{target_label} {ability.capitalize()} save"
        if isinstance(spell_name, str):
            label = f"{label} vs {spell_name}"
    rendered_dice = _attack_dice_views(
        die=die,
        dice=dice,
        selected_index=selected_index,
    )
    return RollView(
        label=label,
        dice=rendered_dice,
        modifier=modifier,
        total=total,
        target=target if isinstance(target, int) else None,
        success=success if isinstance(success, bool) else None,
    )


def _spell_damage_roll_views(event: CombatEvent) -> list[RollView]:
    details = event.data.get("damage_roll_details")
    if not isinstance(details, list):
        detail = event.data.get("damage_roll_detail")
        details = [detail] if isinstance(detail, dict) else []
    views: list[RollView] = []
    spell_name = event.data.get("spell_name")
    for detail in details:
        if not isinstance(detail, dict):
            continue
        label = "Spell Damage"
        target_label = detail.get("target_label")
        if isinstance(target_label, str):
            label = f"{target_label} takes damage"
            if isinstance(spell_name, str):
                label = f"{label} from {spell_name}"
        damage = _pool_roll_view(detail, label=label)
        if damage is not None:
            views.append(damage)
    return views


def _attack_dice_views(
    *,
    die: int,
    dice: object,
    selected_index: object,
) -> tuple[DieView, ...]:
    if (
        isinstance(dice, list)
        and len(dice) >= 1
        and all(isinstance(value, int) for value in dice)
        and isinstance(selected_index, int)
        and 0 <= selected_index < len(dice)
    ):
        return tuple(
            DieView(
                expression="d20",
                value=value,
                selected=index == selected_index,
            )
            for index, value in enumerate(dice)
        )
    return (DieView(expression="d20", value=die),)


def _pool_roll_view(
    detail: object,
    *,
    label: str,
    roll_id: object = None,
    reroll_action_ids: object = None,
) -> RollView | None:
    if not isinstance(detail, dict):
        return None
    expression = detail.get("dice")
    dice_total = detail.get("dice_total")
    modifier = detail.get("modifier", 0)
    total = detail.get("total")
    if not (
        isinstance(expression, str)
        and isinstance(dice_total, int)
        and isinstance(modifier, int)
        and isinstance(total, int)
    ):
        return None
    dice = _individual_dice_views(
        expression,
        detail.get("dice_values"),
        detail.get("die_rolls"),
        reroll_action_ids,
    )
    return RollView(
        label=label,
        dice=dice or (DieView(expression=expression, value=dice_total),),
        modifier=modifier,
        total=total,
        roll_id=roll_id if isinstance(roll_id, str) else None,
    )


def _individual_dice_views(
    expression: str,
    values: object,
    histories: object,
    reroll_action_ids: object,
) -> tuple[DieView, ...]:
    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None or not isinstance(values, list):
        return ()
    count, sides = (int(part) for part in match.groups())
    if len(values) != count or not all(isinstance(value, int) for value in values):
        return ()
    history_values = histories if isinstance(histories, list) else []
    action_ids = reroll_action_ids if isinstance(reroll_action_ids, dict) else {}
    return tuple(
        DieView(
            expression=f"d{sides}",
            value=value,
            history=(
                tuple(history_values[index])
                if index < len(history_values)
                and isinstance(history_values[index], list)
                and all(isinstance(item, int) for item in history_values[index])
                else ()
            ),
            action_id=(
                action_ids.get(str(index))
                if isinstance(action_ids.get(str(index)), str)
                else None
            ),
        )
        for index, value in enumerate(values)
    )
