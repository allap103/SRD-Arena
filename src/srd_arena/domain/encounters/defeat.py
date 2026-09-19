"""Finalize creature defeats and apply rules triggered by them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures.feature_rules.warlock import (
    dark_ones_blessing_temporary_hit_points,
)

from .defeat_prevention import prevent_damage_defeat
from .effect_lifecycle.retargeting import mark_retargetable_effects_for_defeat
from .grappling_state import remove_relationships_for_creature
from .participants import creatures_are_opponents
from .spatial import creature_distance
from .state_runtime import create_event, creature_label

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .encounter_models.resolution import EncounterProgress


def resolve_creature_defeat(
    state: EncounterState,
    creature_ref: str,
    *,
    defeated_by_ref: str | None,
    progress: EncounterProgress,
    action_id: str | None = None,
    frame_id: str | None = None,
) -> bool:
    """Finalize one new defeat and apply source-aware defeat benefits.

    Returning ``False`` for an already finalized or living creature makes the
    boundary safe for damage sequences with several components.
    """

    creature_state = state.creatures[creature_ref]
    if creature_state.is_alive:
        state.pending_lethal_damage.pop(creature_ref, None)
        return False
    if creature_ref in state.defeated_creature_refs:
        return False
    lethal_damage = state.pending_lethal_damage.pop(creature_ref, None)
    if lethal_damage is not None and prevent_damage_defeat(
        state,
        creature_ref,
        lethal_damage,
        progress=progress,
        action_id=action_id,
        frame_id=frame_id,
    ):
        return False
    mark_retargetable_effects_for_defeat(state, creature_ref)
    state.defeated_creature_refs.add(creature_ref)
    remove_relationships_for_creature(state, creature_ref)
    progress.messages.append(("system", f"{creature_state.creature.name} is defeated."))
    progress.events.append(
        create_event(
            state,
            "creature_defeated",
            creature_ref=creature_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={"defeated_by_ref": defeated_by_ref},
        )
    )
    _resolve_dark_ones_blessing(
        state,
        defeated_ref=creature_ref,
        defeated_by_ref=defeated_by_ref,
        progress=progress,
        action_id=action_id,
        frame_id=frame_id,
    )
    return True


def _resolve_dark_ones_blessing(
    state: EncounterState,
    *,
    defeated_ref: str,
    defeated_by_ref: str | None,
    progress: EncounterProgress,
    action_id: str | None,
    frame_id: str | None,
) -> None:
    range_squares = state.definition.grid.distance_from_feet(10, minimum=1)
    for beneficiary_ref, beneficiary_state in state.creatures.items():
        if not beneficiary_state.is_alive or not creatures_are_opponents(
            state, beneficiary_ref, defeated_ref
        ):
            continue
        amount = dark_ones_blessing_temporary_hit_points(beneficiary_state.creature)
        if amount is None:
            continue
        caused_defeat = beneficiary_ref == defeated_by_ref
        witnessed_nearby_defeat = (
            defeated_by_ref is not None
            and creature_distance(state, beneficiary_ref, defeated_ref) <= range_squares
        )
        if not caused_defeat and not witnessed_nearby_defeat:
            continue
        previous = beneficiary_state.creature.temporary_hit_points
        increase = beneficiary_state.creature.grant_temporary_hit_points(amount)
        current = beneficiary_state.creature.temporary_hit_points
        beneficiary_label = creature_label(state, beneficiary_ref)
        if increase > 0:
            progress.messages.append(
                (
                    "system",
                    f"{beneficiary_label} gains {current} Temporary Hit Points "
                    "from Dark One's Blessing.",
                )
            )
        progress.events.append(
            create_event(
                state,
                "feature_triggered",
                creature_ref=beneficiary_ref,
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "feature_id": "dark_ones_blessing",
                    "feature_name": "Dark One's Blessing",
                    "defeated_ref": defeated_ref,
                    "defeated_by_ref": defeated_by_ref,
                    "offered_temporary_hit_points": amount,
                    "previous_temporary_hit_points": previous,
                    "temporary_hit_points": current,
                },
            )
        )
