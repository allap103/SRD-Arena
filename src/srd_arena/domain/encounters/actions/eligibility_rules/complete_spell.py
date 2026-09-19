"""Validate a complete cast before resources, decisions or randomness change."""

from typing import TYPE_CHECKING

from srd_arena.domain.spells.rules import SpellActionPayload, spell_chooses_area_targets

from ..creature_actions.spell_invocation_planning import plan_spell_invocation
from ..option_discovery.spell_areas import spell_area_targets
from ..option_discovery.spell_targets import spell_action_targets
from .models import EligibilityFailure

if TYPE_CHECKING:
    from srd_arena.domain.spells import Spell

    from ...encounter import EncounterState


def complete_spell_failure(
    state: EncounterState, actor_ref: str, payload: SpellActionPayload, spell: Spell
) -> EligibilityFailure | None:
    """Reject incomplete, duplicate, excessive or inconsistent cast configuration."""
    actor = state.creatures[actor_ref].creature
    plan = plan_spell_invocation(state, actor, payload)
    area = spell.geometry_mode in {"point_area", "directional_area"}
    if area and payload.aim_point is None:
        return EligibilityFailure("aim_required", "This spell requires an aim.")
    selects = not area or spell_chooses_area_targets(spell)
    if not selects:
        if payload.target_refs or payload.healing_allocations:
            return EligibilityFailure(
                "invalid_targets", "Area occupants are determined by the engine."
            )
        return None
    refs = payload.target_refs
    if not refs:
        return EligibilityFailure("target_required", "Provide the spell targets.")
    if len(refs) > plan.maximum_targets:
        return EligibilityFailure("target_limit_reached", "Too many spell targets.")
    if not plan.repeat_target_allocations and len(set(refs)) != len(refs):
        return EligibilityFailure(
            "duplicate_target", "This spell requires distinct targets."
        )
    if plan.require_full_target_count and len(refs) != plan.maximum_targets:
        return EligibilityFailure(
            "target_allocation_incomplete", "Allocate every spell effect."
        )
    candidates = (
        spell_area_targets(state, actor, spell, aim_point=payload.aim_point)
        if area
        else spell_action_targets(state, actor, spell)
    )
    available = {t.target_ref for t in candidates}
    if any(ref not in available for ref in refs):
        return EligibilityFailure(
            "target_unavailable", "A target is unavailable for this spell."
        )
    allocations = payload.healing_allocations
    if plan.resource_pool_total is None:
        if allocations:
            return EligibilityFailure(
                "invalid_allocation", "This spell has no allocation pool."
            )
    else:
        amounts = dict(allocations)
        if (
            len(amounts) != len(allocations)
            or set(amounts) != set(refs)
            or any(
                type(amount) is not int
                or amount <= 0
                or amount > plan.resource_allocation_limits.get(ref, 0)
                for ref, amount in allocations
            )
            or sum(amounts.values()) > plan.resource_pool_total
        ):
            return EligibilityFailure(
                "invalid_allocation", "Provide valid target amounts within the pool."
            )
    return None
