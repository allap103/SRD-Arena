from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from srd_arena.application.api import GameEvent


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
    resolution_notes: tuple[str, ...] = ()


def build_roll_views(events: list[GameEvent]) -> list[RollView]:
    views: list[RollView] = []
    resolved_roll_ids = {
        event.data.get("roll_id")
        for event in events
        if event.type == "attack_resolved"
        and isinstance(event.data.get("roll_id"), str)
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
            damage_detail = event.data.get("damage_roll_detail")
            damage = _pool_roll_view(
                damage_detail,
                label=_attack_damage_label(damage_detail),
                roll_id=event.data.get("roll_id"),
                reroll_action_ids=event.data.get("reroll_action_ids"),
            )
            if damage is not None:
                views.append(damage)
            views.extend(
                _additional_attack_damage_roll_views(
                    event.data.get("damage_roll_detail")
                )
            )
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

        if event.type == "invocation_start_checked":
            views.extend(_invocation_start_roll_views(event))
            continue

        if event.type in {"spell_cast", "ongoing_effect_resolved"}:
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


def _attack_roll_view(event: GameEvent) -> RollView | None:
    detail = event.data.get("attack_roll_detail")
    if not isinstance(detail, Mapping):
        return None
    die = detail.get("die")
    dice = detail.get("dice")
    selected_index = detail.get("selected_index")
    modifier = detail.get("modifier")
    total = detail.get("total")
    target = detail.get("target_ac")
    if not (
        isinstance(die, int) and isinstance(modifier, int) and isinstance(total, int)
    ):
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
    hit = event.data.get("hit")
    return RollView(
        label=label,
        dice=rendered_dice,
        modifier=modifier,
        total=total,
        target=target if isinstance(target, int) else None,
        success=hit if isinstance(hit, bool) else None,
    )


def _additional_attack_damage_roll_views(detail: object) -> list[RollView]:
    if not isinstance(detail, Mapping):
        return []
    additional = detail.get("additional_damage")
    if not isinstance(additional, (list, tuple)):
        return []
    views: list[RollView] = []
    for component in additional:
        if not isinstance(component, Mapping):
            continue
        damage_type = component.get("damage_type")
        label = (
            f"{damage_type.capitalize()} damage"
            if isinstance(damage_type, str)
            else "Additional damage"
        )
        view = _pool_roll_view(component, label=label)
        if view is not None:
            views.append(view)
    return views


def _attack_damage_label(detail: object) -> str:
    if not isinstance(detail, Mapping):
        return "Damage"
    damage_type = detail.get("damage_type")
    return (
        f"{damage_type.capitalize()} damage"
        if isinstance(damage_type, str)
        else "Damage"
    )


def _saving_throw_roll_views(event: GameEvent) -> list[RollView]:
    raw_details = event.data.get("save_details")
    if isinstance(raw_details, (list, tuple)):
        details = raw_details
    else:
        detail = event.data.get("save_detail")
        details = (detail,) if isinstance(detail, Mapping) else ()
    views: list[RollView] = []
    spell_name = event.data.get("spell_name")
    for detail in details:
        if not isinstance(detail, Mapping):
            continue
        roll_view = _saving_throw_roll_view(detail, spell_name)
        if roll_view is not None:
            views.append(roll_view)
    return views


def _invocation_start_roll_views(event: GameEvent) -> list[RollView]:
    checks = event.data.get("checks")
    if not isinstance(checks, (list, tuple)):
        return []
    views: list[RollView] = []
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        denominator = check.get("denominator")
        numerator = check.get("numerator")
        roll = check.get("roll")
        failed = check.get("failed")
        if not (
            isinstance(denominator, int)
            and denominator > 0
            and isinstance(numerator, int)
            and isinstance(roll, int)
            and isinstance(failed, bool)
        ):
            continue
        source = check.get("source")
        source_definition_id = (
            source.get("definition_id") if isinstance(source, Mapping) else None
        )
        source_label = (
            source_definition_id.replace("_", " ").replace("-", " ").title()
            if isinstance(source_definition_id, str)
            else source.get("label")
            if isinstance(source, Mapping) and isinstance(source.get("label"), str)
            else None
        )
        check_kind = (
            "spellcasting check"
            if event.data.get("kind") == "cast_spell"
            else "invocation check"
        )
        label = (
            f"{source_label} {check_kind}" if source_label else check_kind.capitalize()
        )
        views.append(
            RollView(
                label=label,
                dice=(DieView(expression=f"d{denominator}", value=roll),),
                modifier=0,
                total=roll,
                target=numerator + 1,
                success=not failed,
            )
        )
    return views


def _saving_throw_roll_view(
    detail: Mapping[str, object],
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
    if not (
        isinstance(die, int) and isinstance(modifier, int) and isinstance(total, int)
    ):
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


def _spell_damage_roll_views(event: GameEvent) -> list[RollView]:
    raw_details = event.data.get("damage_roll_details")
    if isinstance(raw_details, (list, tuple)):
        details = raw_details
    else:
        detail = event.data.get("damage_roll_detail")
        details = (detail,) if isinstance(detail, Mapping) else ()
    views: list[RollView] = []
    spell_name = event.data.get("spell_name")
    for detail in details:
        if not isinstance(detail, Mapping):
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
    integer_dice = (
        tuple(value for value in dice if isinstance(value, int))
        if isinstance(dice, (list, tuple))
        else ()
    )
    if (
        integer_dice
        and isinstance(dice, (list, tuple))
        and len(integer_dice) == len(dice)
        and isinstance(selected_index, int)
        and 0 <= selected_index < len(integer_dice)
    ):
        return tuple(
            DieView(
                expression="d20",
                value=value,
                selected=index == selected_index,
            )
            for index, value in enumerate(integer_dice)
        )
    return (DieView(expression="d20", value=die),)


def _pool_roll_view(
    detail: object,
    *,
    label: str,
    roll_id: object = None,
    reroll_action_ids: object = None,
) -> RollView | None:
    if not isinstance(detail, Mapping):
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
        resolution_notes=_damage_resolution_notes(detail, total),
    )


def _damage_resolution_notes(
    detail: Mapping[str, object],
    rolled_total: int,
) -> tuple[str, ...]:
    notes: list[str] = []
    final_damage = detail.get("final_damage")
    applied_damage = detail.get("applied_damage")
    saved = detail.get("saved")
    if saved is True and isinstance(final_damage, int):
        notes.append(f"Successful save: {final_damage} damage")
    elif isinstance(final_damage, int) and final_damage != rolled_total:
        notes.append(f"Resolved damage: {final_damage}")
    resolved_damage = final_damage if isinstance(final_damage, int) else rolled_total
    if isinstance(applied_damage, int) and applied_damage != resolved_damage:
        notes.append(f"Applied to target: {applied_damage} damage")
    return tuple(notes)


def _individual_dice_views(
    expression: str,
    values: object,
    histories: object,
    reroll_action_ids: object,
) -> tuple[DieView, ...]:
    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None or not isinstance(values, (list, tuple)):
        return ()
    count, sides = (int(part) for part in match.groups())
    integer_values = tuple(value for value in values if isinstance(value, int))
    if len(values) != count or len(integer_values) != len(values):
        return ()
    history_values = histories if isinstance(histories, (list, tuple)) else []
    action_ids = reroll_action_ids if isinstance(reroll_action_ids, Mapping) else {}
    return tuple(
        DieView(
            expression=f"d{sides}",
            value=value,
            history=(
                _integer_tuple(history_values[index])
                if index < len(history_values)
                else ()
            ),
            action_id=(
                action_ids.get(str(index))
                if isinstance(action_ids.get(str(index)), str)
                else None
            ),
        )
        for index, value in enumerate(integer_values)
    )


def _integer_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    integers = tuple(item for item in value if isinstance(item, int))
    return integers if len(integers) == len(value) else ()
