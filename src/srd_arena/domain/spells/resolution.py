from __future__ import annotations

from typing import cast

from ..creatures.feature_rules.types import CapabilityActionResult
from ..geometry import serialize_area
from .custom import resolve_custom_spell
from .resolution_steps.context import (
    DieRoller,
    SpellActionContext,
    SpellTargetContext,
)
from .resolution_steps.follow_ups import resolve_follow_up as _resolve_follow_up
from .resolution_steps.persistent_effects import build_persistent_spell_effects
from .resolution_steps.preparation import prepare_spell_resolution
from .resolution_steps.removals import build_spell_removals
from .resolution_steps.targets import resolve_spell_targets

__all__ = [
    "DieRoller",
    "SpellActionContext",
    "SpellTargetContext",
    "resolve_spell_action",
]


def resolve_spell_action(
    context: SpellActionContext,
) -> CapabilityActionResult | None:
    spell = context.spell
    if spell.definition is not None:
        return resolve_custom_spell(context, _resolve_declarative_spell)
    return None


def _resolve_declarative_spell(
    context: SpellActionContext,
) -> CapabilityActionResult:
    spell = context.spell
    assert context.creature.spellcasting is not None
    assert context.roller is not None

    prepared = prepare_spell_resolution(context)
    resolved_targets = resolve_spell_targets(context, prepared)

    definition = prepared.definition
    targets = prepared.targets
    cast_level = prepared.cast_level

    messages = resolved_targets.messages
    save_details = resolved_targets.save_details
    attack_details = resolved_targets.attack_details
    damage_details = resolved_targets.damage_details
    healing_details = resolved_targets.healing_details
    temporary_hit_point_details = resolved_targets.temporary_hit_point_details

    for sequence_step, follow_up in enumerate(
        definition.follow_ups,
        start=2,
    ):
        follow_up_saves, follow_up_damage = _resolve_follow_up(
            context,
            follow_up,
            cast_level,
            sequence_step,
        )
        save_details.extend(follow_up_saves)
        damage_details.extend(follow_up_damage)

    effects = build_persistent_spell_effects(
        context,
        prepared,
        resolved_targets,
    )

    removals = build_spell_removals(context, resolved_targets)
    messages.extend(removals.messages)
    effects.extend(removals.effects)
    removed_conditions = removals.removed_conditions

    return CapabilityActionResult(
        capability_id=spell.id,
        capability_name=spell.name,
        messages=messages,
        effects=effects,
        details={
            "target_ref": context.target.target_ref,
            "target_label": context.target.target_label,
            "target_refs": [target.target_ref for target in targets],
            "target_labels": [target.target_label for target in targets],
            "affected_target_refs": [
                target.target_ref
                for target in resolved_targets.affected_targets
            ],
            "area": serialize_area(context.area),
            "spell_level": spell.level,
            "slot_level": cast_level,
            "save_detail": save_details[0] if save_details else None,
            "save_details": save_details,
            "attack_roll_detail": attack_details[0] if attack_details else None,
            "attack_roll_details": attack_details,
            "damage_roll_detail": damage_details[0] if damage_details else None,
            "damage_roll_details": damage_details,
            "healing_roll_detail": healing_details[0] if healing_details else None,
            "healing_roll_details": healing_details,
            "temporary_hit_point_detail": (
                temporary_hit_point_details[0] if temporary_hit_point_details else None
            ),
            "temporary_hit_point_details": temporary_hit_point_details,
            "removed_condition": (
                removed_conditions[0] if removed_conditions else None
            ),
            "success": bool(effects)
            or bool(healing_details)
            or bool(temporary_hit_point_details)
            or any(
                isinstance(detail.get("applied_damage"), int)
                and cast(int, detail["applied_damage"]) > 0
                for detail in damage_details
            ),
        },
    )
