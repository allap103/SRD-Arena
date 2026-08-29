"""Project domain action selections into typed engine query details."""

from __future__ import annotations

from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.spells.rules import SpellActionPayload
from srd_arena.engine.queries import (
    ActionOptionDetails,
    DirectTargetOptionDetails,
    FeatureOptionDetails,
    MovementOptionDetails,
    ResourceAllocationOptionDetails,
    SpellOptionDetails,
    StatBlockOptionDetails,
)


def option_details(action: EncounterAction) -> ActionOptionDetails | None:
    """Describe an action without exposing its domain selection payload.

    >>> movement = EncounterAction("Move", "move", value="up")
    >>> option_details(movement)
    MovementOptionDetails(direction='up')
    >>> option_details(EncounterAction("Wait", "wait")) is None
    True
    """

    if action.kind == "spell" and isinstance(action.value, SpellActionPayload):
        payload = action.value
        return SpellOptionDetails(
            source_id=payload.spell_id,
            target_ref=payload.target_ref,
            target_refs=payload.target_refs,
            aim_point=payload.aim_point,
            resource_level=payload.slot_level,
            selected_condition=payload.selected_condition,
            selected_damage_type=payload.selected_damage_type,
            selected_ability=payload.selected_ability,
            healing_allocations=payload.healing_allocations,
        )
    if action.kind == "toggle_spell_target":
        return SpellOptionDetails(
            source_id=action.source_trigger_id,
            target_ref=action.value if isinstance(action.value, str) else None,
            target_refs=((action.value,) if isinstance(action.value, str) else ()),
            aim_point=None,
            resource_level=None,
            selected_condition=None,
            selected_damage_type=None,
            selected_ability=None,
            healing_allocations=(),
        )
    if action.kind == "stat_block":
        return StatBlockOptionDetails(
            source_id=action.preferred_attack_name,
            target_ref=_direct_target_ref(action.value),
        )
    if action.kind == "feature" and isinstance(action.value, str):
        return FeatureOptionDetails(feature_id=action.value)
    if action.kind == "move" and isinstance(action.value, str):
        return MovementOptionDetails(direction=action.value)
    if action.kind == "set_spell_resource_allocation" and isinstance(
        action.value,
        str,
    ):
        target_ref, separator, _amount = action.value.rpartition("~")
        return ResourceAllocationOptionDetails(
            target_ref=target_ref if separator else action.value
        )
    if action.kind in {
        "attack",
        "grapple",
        "opportunity_attack",
        "wake_spell_target",
    }:
        return DirectTargetOptionDetails(target_ref=_direct_target_ref(action.value))
    return None


def _direct_target_ref(
    value: str | int | tuple[float, float] | SpellActionPayload | None,
) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"participant:{value}"
    return None
