"""Apply encounter consequences after source-neutral spell resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures.feature_rules.types import CapabilityActionResult
from ....effects import serialize_effects
from ....spells.resolution import SpellTargetContext
from ...encounter_models.resolution import EncounterProgress
from ...ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)
from ...state_runtime import apply_encounter_effects, create_event

if TYPE_CHECKING:
    from ....creatures import Spellcasting
    from ....spells.definitions import Spell
    from ...encounter import EncounterState


def apply_spell_result(
    state: EncounterState,
    *,
    spellcasting: Spellcasting,
    spell: Spell,
    cast_level: int | None,
    creature_ref: str,
    action_id: str,
    result: CapabilityActionResult,
    progress: EncounterProgress,
    target_ref: str | None,
    target: SpellTargetContext,
) -> None:
    """Publish resolved effects and record the completed cast.

    The encounter-facing event preserves spell metadata alongside the generic
    capability result so frontends do not need to inspect domain objects.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.creatures.feature_rules.types import CapabilityActionResult
    >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
    >>> from srd_arena.domain.spells import Spell
    >>> state = SimpleNamespace(event_sequence=1)
    >>> result = CapabilityActionResult("fire-bolt", "Fire Bolt", [], [])
    >>> progress = EncounterProgress()
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.spell_runtime.aftermath."
    ...     "apply_encounter_effects", return_value=[]
    ... ):
    ...     apply_spell_result(
    ...         state,
    ...         spellcasting=SimpleNamespace(spell_slots_remaining={}),
    ...         spell=Spell("fire-bolt", "Fire Bolt", None, 0),
    ...         cast_level=None,
    ...         creature_ref="mage",
    ...         action_id="cast",
    ...         result=result,
    ...         progress=progress,
    ...         target_ref="dummy",
    ...         target=SimpleNamespace(target_label="Dummy"),
    ...     )
    >>> (progress.events[0].type, progress.events[0].data["spell_id"])
    ('spell_cast', 'fire-bolt')
    """

    progress.messages.extend(result.messages)
    _apply_damage_lifecycle(
        state,
        result,
        creature_ref=creature_ref,
        progress=progress,
    )
    progress.messages.extend(
        apply_encounter_effects(state, result.effects, origin_id=action_id)
    )
    progress.events.append(
        create_event(
            state,
            "spell_cast",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "spell",
                "spell_id": result.capability_id,
                "spell_name": result.capability_name,
                "spell_level": result.details.get("spell_level", spell.level),
                "target_ref": result.details.get("target_ref", target_ref),
                "target_label": result.details.get("target_label", target.target_label),
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
