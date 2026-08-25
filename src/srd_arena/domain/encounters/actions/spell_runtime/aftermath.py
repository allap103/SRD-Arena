"""Apply encounter consequences after source-neutral spell resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures.feature_rules.types import CapabilityActionResult
from ....effects import serialize_effects
from ....effects.runtime import OngoingEffectKind
from ....spells.resolution import SpellTargetContext
from ...models import ActionCost, EncounterProgress
from ...ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)

if TYPE_CHECKING:
    from ....creatures import Creature, Spellcasting
    from ....spells.definitions import Spell
    from ...encounter import EncounterState


def apply_spell_result(
    state: EncounterState,
    *,
    actor: Creature,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None,
    creature_ref: str,
    action_id: str,
    result: CapabilityActionResult,
    progress: EncounterProgress,
    target_ref: str | None,
    target: SpellTargetContext,
) -> None:
    """Spend resources, publish lifecycle effects, and record the cast event."""

    state._spend_spell_resources(spellcasting, spell, cost, cast_level)
    progress.messages.extend(result.messages)
    _apply_damage_lifecycle(
        state,
        result,
        creature_ref=creature_ref,
        progress=progress,
    )
    resolve_spell_lifecycle_event(
        state,
        "target_casts_spell",
        actor_ref=creature_ref,
        progress=progress,
    )
    _log_replaced_concentration(
        state,
        actor,
        result,
        creature_ref=creature_ref,
        progress=progress,
    )
    progress.messages.extend(
        state._apply_effects(result.effects, origin_id=action_id)
    )
    progress.events.append(
        state._event(
            "spell_cast",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "spell",
                "spell_id": result.capability_id,
                "spell_name": result.capability_name,
                "spell_level": result.details.get("spell_level", spell.level),
                "target_ref": result.details.get("target_ref", target_ref),
                "target_label": result.details.get(
                    "target_label", target.target_label
                ),
                "target_refs": result.details.get("target_refs"),
                "target_labels": result.details.get("target_labels"),
                "area": result.details.get("area"),
                "slot_level": result.details.get("slot_level", spell.level),
                "spell_slots_remaining": (
                    spellcasting.spell_slots_remaining.get(
                        cast_level if cast_level is not None else spell.level,
                        0,
                    )
                    if spell.level > 0
                    else None
                ),
                "save_detail": result.details.get("save_detail"),
                "save_details": result.details.get("save_details"),
                "attack_roll_detail": result.details.get("attack_roll_detail"),
                "attack_roll_details": result.details.get("attack_roll_details"),
                "damage_roll_detail": result.details.get("damage_roll_detail"),
                "damage_roll_details": result.details.get("damage_roll_details"),
                "healing_roll_detail": result.details.get("healing_roll_detail"),
                "healing_roll_details": result.details.get("healing_roll_details"),
                "temporary_hit_point_detail": result.details.get(
                    "temporary_hit_point_detail"
                ),
                "temporary_hit_point_details": result.details.get(
                    "temporary_hit_point_details"
                ),
                "effects": serialize_effects(result.effects),
                "success": result.details.get("success", False),
            },
        )
    )


def _apply_damage_lifecycle(
    state: EncounterState,
    result: CapabilityActionResult,
    *,
    creature_ref: str,
    progress: EncounterProgress,
) -> None:
    damage_details = result.details.get("damage_roll_details")
    if not isinstance(damage_details, list):
        return
    for detail in damage_details:
        if not isinstance(detail, dict):
            continue
        damaged_ref = detail.get("target_ref")
        applied_damage = detail.get("applied_damage")
        if not isinstance(damaged_ref, str) or not isinstance(applied_damage, int):
            continue
        if applied_damage > 0:
            resolve_spell_lifecycle_event(
                state,
                "target_damaged",
                actor_ref=creature_ref,
                target_ref=damaged_ref,
                progress=progress,
            )
            resolve_spell_lifecycle_event(
                state,
                "target_deals_damage",
                actor_ref=creature_ref,
                target_ref=damaged_ref,
                progress=progress,
            )
        resolve_concentration_damage(
            state,
            damaged_ref,
            applied_damage,
            progress,
        )


def _log_replaced_concentration(
    state: EncounterState,
    actor: Creature,
    result: CapabilityActionResult,
    *,
    creature_ref: str,
    progress: EncounterProgress,
) -> None:
    starts_concentration = any(
        effect.kind == "start_ongoing_effect"
        and effect.data.get("effect_kind") == "concentration"
        for effect in result.effects
    )
    if not starts_concentration:
        return
    for existing in state.ongoing_effects:
        if (
            existing.kind is OngoingEffectKind.CONCENTRATION
            and existing.identity.source.applied_by_ref == creature_ref
        ):
            effect_label = existing.parameters.get("effect_label")
            if not isinstance(effect_label, str):
                effect_label = existing.identity.source.definition_id.replace(
                    "_", " "
                ).title()
            progress.messages.append(
                (
                    "system",
                    f"{actor.name} drops concentration on {effect_label}.",
                )
            )

