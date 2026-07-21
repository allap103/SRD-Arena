from __future__ import annotations

from collections.abc import Callable

from .features.types import EffectResult
from ..status import Status, build_named_status

ApplyStatus = Callable[[Status], None]
RemoveStatus = Callable[[str, str], None]


def apply_effects(
    effects: list[EffectResult],
    *,
    apply_status: ApplyStatus,
    remove_status: RemoveStatus,
) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for effect in effects:
        if effect.kind == "apply_status":
            apply_status(_status_from_effect(effect))
        elif effect.kind == "remove_status":
            remove_status(effect.target_ref, _required_status_name(effect))
        elif effect.kind == "message":
            messages.extend(message_effects(effect))
        else:
            raise ValueError(f"Unsupported effect kind: {effect.kind}")
    return messages


def message_effects(effect: EffectResult) -> list[tuple[str, str]]:
    channel = effect.data.get("channel", "system")
    text = effect.data.get("text")
    if not isinstance(channel, str) or not isinstance(text, str):
        raise ValueError("message effect requires string channel and text.")
    return [(channel, text)]


def serialize_effects(effects: list[EffectResult]) -> list[dict[str, object]]:
    return [
        {
            "kind": effect.kind,
            "target_ref": effect.target_ref,
            "success": effect.success,
            "data": effect.data,
        }
        for effect in effects
    ]


def _status_from_effect(effect: EffectResult) -> Status:
    source_ref = effect.data.get("source_ref")
    source_label = effect.data.get("source_label")
    if not isinstance(source_ref, str) or not isinstance(source_label, str):
        raise ValueError("apply_status effect requires source identity.")
    return build_named_status(
        name=_required_status_name(effect),
        source_ref=source_ref,
        source_label=source_label,
        target_ref=effect.target_ref,
        expires_on_creature_ref=(
            effect.data.get("expires_on_creature_ref")
            if isinstance(effect.data.get("expires_on_creature_ref"), str)
            else None
        ),
        expires_on_round=(
            effect.data.get("expires_on_round")
            if isinstance(effect.data.get("expires_on_round"), int)
            else None
        ),
    )


def _required_status_name(effect: EffectResult) -> str:
    for key in ("status_name", "condition", "name"):
        value = effect.data.get(key)
        if isinstance(value, str):
            return value
    raise ValueError(f"{effect.kind} effect requires a status_name.")
