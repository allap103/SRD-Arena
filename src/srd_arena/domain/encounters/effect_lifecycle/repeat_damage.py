"""Resolve damage dealt when a creature fails an ongoing-effect save."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...rolls.dice import resolve_dice
from .concentration import resolve_concentration_damage
from .lifecycle_events import resolve_spell_lifecycle_event

if TYPE_CHECKING:
    from ...creatures import Creature
    from ...effects.runtime import OngoingEffect
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def resolve_repeat_failure_damage(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
    target: Creature,
    progress: EncounterProgress | None,
) -> list[dict[str, object]]:
    """Apply and describe all damage caused by one failed repeat save."""

    repeat_save = effect.lifecycle.repeat_save
    if repeat_save is None:
        return []
    effect_label = (
        effect.label or effect.identity.source.definition_id.replace("_", " ").title()
    )
    details: list[dict[str, object]] = []
    for damage in repeat_save.failure_damage:
        count_text, separator, sides_text = damage.dice.partition("d")
        if not separator or not count_text.isdigit() or not sides_text.isdigit():
            continue
        source_ref = effect.identity.source.applied_by_ref
        damage_modifier = (
            state.combat_rules.roll_modifiers(
                state,
                source_ref,
                "damage_roll",
            ).resolve_modifier(state.dice.roll_die)
            if source_ref in state.creatures
            else 0
        )
        roll = resolve_dice(
            int(count_text),
            int(sides_text),
            modifier=damage_modifier,
            roller=state.dice.roll_die,
        )
        applied = state.combat_rules.apply_damage(
            state,
            creature_ref,
            roll.total,
            damage.damage_type,
        )
        details.append(
            {
                "target_ref": creature_ref,
                "target_label": target.name,
                "dice": damage.dice,
                "dice_values": [die.result for die in roll.dice],
                "die_rolls": [list(die.rolls) for die in roll.dice],
                "dice_total": roll.subtotal,
                "modifier": roll.modifier,
                "total": roll.total,
                "damage_type": damage.damage_type,
                "applied_damage": applied,
            }
        )
        if progress is not None:
            progress.messages.append(
                (
                    "system",
                    f"{effect_label} deals "
                    f"{applied} {damage.damage_type} damage to {target.name}.",
                )
            )
        resolve_spell_lifecycle_event(
            state,
            "target_damaged",
            actor_ref=source_ref or "system",
            target_ref=creature_ref,
            progress=progress,
        )
        resolve_concentration_damage(state, creature_ref, applied, progress)
    return details
