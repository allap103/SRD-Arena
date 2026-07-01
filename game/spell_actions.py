from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .encounter_geometry import AreaOfEffect, serialize_area
from .features.types import CapabilityActionResult, EffectResult
from .models.actor import Actor
from .models.spellcasting import Spell
from .systems.saving_throw import resolve_saving_throw

DieRoller = Callable[[int], int]


@dataclass(frozen=True)
class SpellTargetContext:
    actor: Actor
    target_ref: str
    target_label: str
    target_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpellActionContext:
    actor: Actor
    spell: Spell
    target: SpellTargetContext
    current_round: int
    targets: tuple[SpellTargetContext, ...] = ()
    area: AreaOfEffect | None = None
    source_ref: str = "player"
    roller: DieRoller | None = None


def resolve_spell_action(
    context: SpellActionContext,
) -> CapabilityActionResult | None:
    spell = context.spell
    if spell.id == "color_spray":
        return _resolve_color_spray(context)
    if spell.id == "lesser_restoration":
        return _resolve_lesser_restoration(context)
    return None


def _resolve_color_spray(context: SpellActionContext) -> CapabilityActionResult:
    actor = context.actor
    spell = context.spell
    assert actor.spellcasting is not None
    assert context.roller is not None
    ability = (
        spell.saving_throw_abilities[0]
        if spell.saving_throw_abilities
        else "constitution"
    )
    targets = context.targets or (context.target,)
    messages = [("system", f"{actor.name} casts {spell.name} on {context.target.target_label}.")]
    effects: list[EffectResult] = []
    save_details: list[dict[str, object]] = []
    for target in targets:
        save_result = resolve_saving_throw(
            target.actor,
            ability,
            actor.spellcasting.save_dc,
            roller=context.roller,
        )
        save_detail = {
            "target_ref": target.target_ref,
            "target_label": target.target_label,
            "ability": ability,
            "proficient": save_result.proficient,
            "die": save_result.check.roll.selected,
            "dice": list(save_result.check.roll.dice),
            "selected_index": save_result.check.roll.selected_index,
            "mode": save_result.check.roll.mode,
            "modifier": save_result.modifiers.total,
            "ability_modifier": save_result.modifiers.ability,
            "proficiency_modifier": save_result.modifiers.proficiency,
            "other_modifier": save_result.modifiers.other,
            "total": save_result.check.roll.total,
            "target_dc": save_result.check.target,
            "success": save_result.check.success,
        }
        save_details.append(save_detail)
        messages.append(
            (
                "system",
                f"{target.target_label} makes a Constitution save: d20={save_result.check.roll.selected} "
                f"+ {save_result.modifiers.total} = {save_result.check.roll.total} "
                f"vs DC {actor.spellcasting.save_dc}.",
            ),
        )
        if save_result.check.success:
            messages.append(("system", f"{target.target_label} shrugs off the dazzling light."))
            continue
        messages.append(
            ("system", f"{target.target_label} is blinded until the end of your next turn.")
        )
        effects.append(
            EffectResult(
                kind="apply_status",
                target_ref=target.target_ref,
                data={
                    "status_name": "blinded",
                    "condition": "blinded",
                    "source_ref": context.source_ref,
                    "source_label": actor.name,
                    "expires_on_actor_ref": context.source_ref,
                    "expires_on_round": context.current_round + 1,
                    "target_label": target.target_label,
                    "save_detail": save_detail,
                },
            )
        )

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
            "area": serialize_area(context.area),
            "spell_level": spell.level,
            "slot_level": spell.level,
            "save_detail": save_details[0] if save_details else None,
            "save_details": save_details,
            "success": any(not detail["success"] for detail in save_details),
        },
    )


def _resolve_lesser_restoration(context: SpellActionContext) -> CapabilityActionResult:
    actor = context.actor
    spell = context.spell
    target_ref = context.target.target_ref
    target_label = context.target.target_label
    removable = spell.removable_conditions
    removed_condition = next(
        (
            condition
            for condition in context.target.target_conditions
            if condition in removable
        ),
        None,
    )
    messages = [("system", f"{actor.name} casts {spell.name} on {target_label}.")]
    effects: list[EffectResult] = []
    if removed_condition is None:
        messages.append(
            ("system", f"No removable condition on {target_label.lower()} is affected.")
        )
        success = False
    else:
        messages.append(
            ("system", f"{target_label} is no longer {removed_condition}.")
        )
        effects.append(
            EffectResult(
                kind="remove_status",
                target_ref=target_ref,
                data={"condition": removed_condition},
            )
        )
        success = True

    return CapabilityActionResult(
        capability_id=spell.id,
        capability_name=spell.name,
        messages=messages,
        effects=effects,
        details={
            "target_ref": target_ref,
            "target_label": target_label,
            "spell_level": spell.level,
            "slot_level": spell.level,
            "removed_condition": removed_condition,
            "success": success,
        },
    )
