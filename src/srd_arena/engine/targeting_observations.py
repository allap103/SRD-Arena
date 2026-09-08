"""Project staged spell choices without confusing them with started casts."""

from dataclasses import replace

from srd_arena.domain.encounters.encounter import EncounterState

from .observation_models import (
    TargetingObservation,
    TargetResourceAllocationObservation,
    TargetResourceLimitObservation,
)


def observe_targeting(state: EncounterState) -> TargetingObservation | None:
    """Snapshot the complete staged selection for privileged clients."""

    pending = state.interrupts.pending_spell_cast
    if pending is None:
        return None
    actor = state.creatures[state.current_decision().creature_ref].creature
    spell = (
        next(
            (
                spell
                for spell in actor.spellcasting.learned_spells
                if spell.id == pending.spell_id
            ),
            None,
        )
        if actor.spellcasting is not None
        else None
    )
    return TargetingObservation(
        source_id=pending.spell_id,
        source_label=spell.name if spell is not None else pending.spell_id,
        selected_target_refs=tuple(pending.selected_target_refs),
        maximum_targets=pending.maximum_targets,
        repeat_target_allocations=pending.repeat_target_allocations,
        require_full_target_count=pending.require_full_target_count,
        resource_pool_total=pending.resource_pool_total,
        resource_allocations=tuple(
            TargetResourceAllocationObservation(target_ref=target_ref, amount=amount)
            for target_ref, amount in pending.resource_allocations.items()
        ),
        resource_limits=tuple(
            TargetResourceLimitObservation(target_ref=target_ref, maximum=maximum)
            for target_ref, maximum in pending.resource_allocation_limits.items()
        ),
    )


def observe_player_targeting(
    state: EncounterState,
    allied_refs: frozenset[str],
) -> TargetingObservation | None:
    """Expose only this team's active selection and allied allocation limits.

    Selected references and amounts are the player's own input, so they remain
    known if a previously chosen creature leaves sight. They reveal no updated
    enemy statistics or positions. A nested decision must not expose a suspended
    cast as though it were currently accepting target input.
    """

    decision = state.current_decision()
    pending = state.interrupts.pending_spell_cast
    if (
        decision.kind != "spell_targets"
        or decision.creature_ref not in allied_refs
        or pending is None
        or pending.action.creature_ref != decision.creature_ref
    ):
        return None
    targeting = observe_targeting(state)
    assert targeting is not None
    return replace(
        targeting,
        resource_limits=tuple(
            limit
            for limit in targeting.resource_limits
            if limit.target_ref in allied_refs
        ),
    )
