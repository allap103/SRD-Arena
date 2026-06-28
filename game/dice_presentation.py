from __future__ import annotations

from dataclasses import dataclass

from .encounter import CombatEvent


@dataclass(frozen=True)
class DieView:
    expression: str
    value: int
    selected: bool = True
    history: tuple[int, ...] = ()


@dataclass(frozen=True)
class RollView:
    label: str
    dice: tuple[DieView, ...]
    modifier: int
    total: int
    target: int | None = None
    success: bool | None = None


def build_roll_views(events: list[CombatEvent]) -> list[RollView]:
    views: list[RollView] = []
    for event in events:
        if event.type == "attack_resolved":
            attack = _attack_roll_view(event)
            if attack is not None:
                views.append(attack)
            damage = _pool_roll_view(
                event.data.get("damage_roll_detail"),
                label="Damage",
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
        )
    ]


def _attack_roll_view(event: CombatEvent) -> RollView | None:
    detail = event.data.get("attack_roll_detail")
    if not isinstance(detail, dict):
        return None
    die = detail.get("die")
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
    return RollView(
        label=label,
        dice=(DieView(expression="d20", value=die),),
        modifier=modifier,
        total=total,
        target=target if isinstance(target, int) else None,
        success=event.data.get("hit") if isinstance(event.data.get("hit"), bool) else None,
    )


def _pool_roll_view(detail: object, *, label: str) -> RollView | None:
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
    return RollView(
        label=label,
        dice=(DieView(expression=expression, value=dice_total),),
        modifier=modifier,
        total=total,
    )
