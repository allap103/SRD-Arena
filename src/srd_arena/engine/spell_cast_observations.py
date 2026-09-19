"""Project spell preparation requirements without opening a game decision."""

from srd_arena.domain.encounters.actions.creature_actions.spell_invocation_planning import (
    plan_spell_invocation,
)
from srd_arena.domain.encounters.actions.option_discovery.spell_areas import (
    spell_area_targets,
)
from srd_arena.domain.encounters.actions.option_discovery.spell_targets import (
    spell_action_targets,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.spells.rules import SpellActionPayload, spell_chooses_area_targets

from .queries import ActionOption, SpellOptionDetails
from .spell_cast_observation_models import SpellCastOptions


def observe_spell_cast_options(
    state: EncounterState | None, option: ActionOption
) -> SpellCastOptions | None:
    """Describe target choices as read-only facts, with no staged domain state."""
    details = option.details
    if state is None or not isinstance(details, SpellOptionDetails):
        return None
    actor = state.creatures[option.creature_ref].creature
    payload = SpellActionPayload(
        spell_id=details.source_id or "",
        target_refs=details.target_refs,
        aim_point=details.aim_point,
        slot_level=details.resource_level,
        grant_id=details.grant_id,
    )
    plan = plan_spell_invocation(state, actor, payload)
    spell = plan.spell
    if spell is None:
        return None
    selects = spell.geometry_mode not in {
        "point_area",
        "directional_area",
    } or spell_chooses_area_targets(spell)
    refs = (
        tuple(t.target_ref for t in spell_action_targets(state, actor, spell))
        if selects
        else ()
    )
    initial = details.target_refs
    if selects and spell_chooses_area_targets(spell) and details.aim_point is not None:
        refs = tuple(
            t.target_ref
            for t in spell_area_targets(
                state, actor, spell, aim_point=details.aim_point
            )
        )
        initial = refs[: plan.maximum_targets]
    return SpellCastOptions(
        refs,
        initial,
        plan.maximum_targets,
        plan.repeat_target_allocations,
        plan.require_full_target_count,
        selects,
        plan.resource_pool_total,
        tuple(plan.resource_allocation_limits.items()),
        bool(
            selects
            and spell_chooses_area_targets(spell)
            and spell.definition
            and spell.definition.target.count.maximum == "all"
        ),
    )
