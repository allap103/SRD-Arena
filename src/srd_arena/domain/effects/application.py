from __future__ import annotations

from collections.abc import Callable

from .conditions import AppliedCondition, Condition, build_applied_condition
from .results import EffectResult
from .rule_effects import serialize_runtime_rule_effect
from .runtime import EffectSourceKind

ApplyCondition = Callable[[AppliedCondition], object]
RemoveCondition = Callable[[str, Condition], None]
ApplyOngoingEffect = Callable[[EffectResult, str], object]
RemoveOngoingEffects = Callable[[EffectResult], object]


def apply_effects(
    effects: list[EffectResult],
    *,
    apply_condition: ApplyCondition,
    remove_condition: RemoveCondition,
    apply_ongoing_effect: ApplyOngoingEffect | None = None,
    remove_ongoing_effects: RemoveOngoingEffects | None = None,
    origin_id: str | None = None,
) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for effect in effects:
        if effect.kind == "apply_condition":
            apply_condition(
                condition_from_effect_with_origin(
                    effect,
                    origin_id=origin_id,
                )
            )
        elif effect.kind == "remove_condition":
            remove_condition(
                effect.target_ref,
                Condition(_required_condition_name(effect)),
            )
        elif effect.kind == "start_ongoing_effect":
            if apply_ongoing_effect is None:
                raise ValueError("No ongoing-effect application service provided.")
            apply_ongoing_effect(effect, origin_id or "")
        elif effect.kind == "remove_ongoing_effects":
            if remove_ongoing_effects is None:
                raise ValueError("No ongoing-effect removal service provided.")
            remove_ongoing_effects(effect)
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
    return [_serialize_effect(effect) for effect in effects]


def _serialize_effect(effect: EffectResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": effect.kind,
        "target_ref": effect.target_ref,
        "success": effect.success,
        "data": effect.data,
    }
    if effect.rule_effects:
        payload["rule_effects"] = [
            serialize_runtime_rule_effect(rule_effect)
            for rule_effect in effect.rule_effects
        ]
    return payload


def condition_from_effect(effect: EffectResult) -> AppliedCondition:
    return condition_from_effect_with_origin(effect, origin_id=None)


def condition_from_effect_with_origin(
    effect: EffectResult,
    *,
    origin_id: str | None,
) -> AppliedCondition:
    source_ref = effect.data.get("source_ref")
    source_label = effect.data.get("source_label")
    if not isinstance(source_ref, str) or not isinstance(source_label, str):
        raise ValueError("apply_condition effect requires source identity.")
    expires_on_creature_ref = effect.data.get("expires_on_creature_ref")
    expires_on_round = effect.data.get("expires_on_round")
    metadata = effect.data.get("metadata")
    source_kind = effect.data.get("source_kind", "creature")
    definition_id = effect.data.get("definition_id")
    parent_effect_kind = effect.data.get("parent_effect_kind")
    parent_id = (
        f"ongoing:{parent_effect_kind}:{origin_id}"
        if isinstance(parent_effect_kind, str) and origin_id is not None
        else None
    )
    return build_applied_condition(
        condition=Condition(_required_condition_name(effect)),
        source_ref=source_ref,
        source_label=source_label,
        target_ref=effect.target_ref,
        expires_on_creature_ref=(
            expires_on_creature_ref
            if isinstance(expires_on_creature_ref, str)
            else None
        ),
        expires_on_round=(
            expires_on_round if isinstance(expires_on_round, int) else None
        ),
        metadata=metadata if isinstance(metadata, dict) else None,
        source_kind=EffectSourceKind(str(source_kind)),
        definition_id=(definition_id if isinstance(definition_id, str) else source_ref),
        origin_id=origin_id,
        parent_id=parent_id,
        root_id=parent_id,
    )


def _required_condition_name(effect: EffectResult) -> str:
    for key in ("status_name", "condition", "name"):
        value = effect.data.get(key)
        if isinstance(value, str):
            return value
    raise ValueError(f"{effect.kind} effect requires a condition name.")
