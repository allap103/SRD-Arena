from __future__ import annotations

from collections.abc import Callable

from .features.types import CapabilityActionResult, EffectResult
from .models.actor import Actor
from .models.spellcasting import Spell
from .systems.saving_throw import resolve_saving_throw

DieRoller = Callable[[int], int]


def resolve_spell_action(
    actor: Actor,
    spell: Spell,
    target: Actor,
    *,
    target_ref: str,
    target_label: str,
    target_conditions: tuple[str, ...] = (),
    current_round: int,
    source_ref: str = "player",
    roller: DieRoller,
) -> CapabilityActionResult | None:
    if spell.id == "color_spray":
        return _resolve_color_spray(
            actor,
            spell,
            target,
            target_ref=target_ref,
            target_label=target_label,
            target_conditions=target_conditions,
            current_round=current_round,
            source_ref=source_ref,
            roller=roller,
        )
    if spell.id == "lesser_restoration":
        return _resolve_lesser_restoration(
            actor,
            spell,
            target,
            target_ref=target_ref,
            target_label=target_label,
            target_conditions=target_conditions,
        )
    return None


def _resolve_color_spray(
    actor: Actor,
    spell: Spell,
    target: Actor,
    *,
    target_ref: str,
    target_label: str,
    current_round: int,
    source_ref: str,
    roller: DieRoller,
) -> CapabilityActionResult:
    assert actor.spellcasting is not None
    ability = (
        spell.saving_throw_abilities[0]
        if spell.saving_throw_abilities
        else "constitution"
    )
    save_result = resolve_saving_throw(
        target,
        ability,
        actor.spellcasting.save_dc,
        roller=roller,
    )
    save_detail = {
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
    messages = [
        ("system", f"{actor.name} casts {spell.name} on {target_label}."),
        (
            "system",
            f"{target_label} makes a Constitution save: d20={save_result.check.roll.selected} "
            f"+ {save_result.modifiers.total} = {save_result.check.roll.total} "
            f"vs DC {actor.spellcasting.save_dc}.",
        ),
    ]
    effects: list[EffectResult] = []
    if save_result.check.success:
        messages.append(("system", f"{target_label} shrugs off the dazzling light."))
    else:
        messages.append(
            ("system", f"{target_label} is blinded until the end of your next turn.")
        )
        effects.append(
            EffectResult(
                kind="apply_status",
                target_ref=target_ref,
                data={
                    "status_name": "blinded",
                    "condition": "blinded",
                    "source_ref": source_ref,
                    "source_label": actor.name,
                    "expires_on_actor_ref": source_ref,
                    "expires_on_round": current_round + 1,
                    "target_label": target_label,
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
            "target_ref": target_ref,
            "target_label": target_label,
            "spell_level": spell.level,
            "slot_level": spell.level,
            "save_detail": save_detail,
            "success": not save_result.check.success,
        },
    )


def _resolve_lesser_restoration(
    actor: Actor,
    spell: Spell,
    target: Actor,
    *,
    target_ref: str,
    target_label: str,
    target_conditions: tuple[str, ...],
) -> CapabilityActionResult:
    removable = spell.removable_conditions
    removed_condition = next(
        (condition for condition in target_conditions if condition in removable),
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
