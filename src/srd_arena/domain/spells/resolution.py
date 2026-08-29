"""Coordinate capability-driven and custom spell resolution into effect output."""

from __future__ import annotations

from typing import cast

from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    DamageApplication,
    SpellResolutionDetails,
)
from srd_arena.domain.geometry import serialize_area

from .custom import resolve_custom_spell
from .resolution_steps.context import (
    SpellActionContext,
    SpellResolutionEnvironment,
    SpellTargetContext,
)
from .resolution_steps.follow_ups import resolve_follow_up as _resolve_follow_up
from .resolution_steps.persistent_effects import build_persistent_spell_effects
from .resolution_steps.preparation import prepare_spell_resolution
from .resolution_steps.removals import build_spell_removals
from .resolution_steps.targets import resolve_spell_targets

__all__ = [
    "SpellActionContext",
    "SpellResolutionEnvironment",
    "SpellTargetContext",
    "resolve_spell_action",
]


def resolve_spell_action(
    context: SpellActionContext,
) -> ActionResolutionResult | None:
    """Execute a configured spell invocation through its declarative or custom resolver.

    Metadata-only spells have no executable action result.

    >>> from types import SimpleNamespace
    >>> from .definitions import Spell
    >>> context = SimpleNamespace(
    ...     spell=Spell("legend_lore", "Legend Lore", "XPHB", 5)
    ... )
    >>> resolve_spell_action(context) is None
    True
    """

    spell = context.spell
    if spell.definition is not None:
        return resolve_custom_spell(context, _resolve_declarative_spell)
    return None


def _resolve_declarative_spell(
    context: SpellActionContext,
) -> ActionResolutionResult:
    spell = context.spell
    assert context.creature.spellcasting is not None

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

    return ActionResolutionResult(
        definition_id=spell.id,
        definition_name=spell.name,
        messages=messages,
        effects=effects,
        details=SpellResolutionDetails(
            target_ref=context.target.target_ref,
            target_label=context.target.target_label,
            targets=tuple(
                (target.target_ref, target.target_label) for target in targets
            ),
            affected_target_refs=tuple(
                target.target_ref for target in resolved_targets.affected_targets
            ),
            area=serialize_area(context.area),
            spell_level=spell.level,
            slot_level=cast_level,
            save_details=tuple(save_details),
            attack_roll_details=tuple(attack_details),
            damage_roll_details=tuple(damage_details),
            healing_roll_details=tuple(healing_details),
            temporary_hit_point_details=tuple(temporary_hit_point_details),
            damage_applications=tuple(
                DamageApplication(
                    target_ref=cast(str, detail["target_ref"]),
                    amount=cast(int, detail["applied_damage"]),
                )
                for detail in damage_details
            ),
            success=bool(effects)
            or bool(healing_details)
            or bool(temporary_hit_point_details)
            or any(
                isinstance(detail.get("applied_damage"), int)
                and cast(int, detail["applied_damage"]) > 0
                for detail in damage_details
            ),
        ),
    )
