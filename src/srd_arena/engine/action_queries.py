"""Normalize encoded domain actions into typed engine query details."""

from __future__ import annotations

from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.spells.rules import (
    parse_spell_action_ability,
    parse_spell_action_condition,
    parse_spell_action_damage_type,
    parse_spell_action_slot,
    parse_spell_action_targets,
    parse_spell_action_value,
    parse_spell_healing_allocations,
)
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
    """Describe an action without exposing its overloaded encoded value.

    >>> movement = EncounterAction("Move", "move", value="up")
    >>> option_details(movement)
    MovementOptionDetails(direction='up')
    >>> option_details(EncounterAction("Wait", "wait")) is None
    True
    """

    if action.kind == "spell" and isinstance(action.value, str):
        source_id, target_ref, aim_point = parse_spell_action_value(action.value)
        return SpellOptionDetails(
            source_id=source_id,
            target_ref=target_ref,
            target_refs=parse_spell_action_targets(action.value),
            aim_point=aim_point,
            resource_level=parse_spell_action_slot(action.value),
            selected_condition=parse_spell_action_condition(action.value),
            selected_damage_type=parse_spell_action_damage_type(action.value),
            selected_ability=parse_spell_action_ability(action.value),
            healing_allocations=tuple(
                sorted(parse_spell_healing_allocations(action.value).items())
            ),
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
    value: str | int | tuple[float, float] | None,
) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"participant:{value}"
    return None
