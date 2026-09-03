"""Apply encounter-state consequences specific to the Prone condition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import size_rank
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.runtime import EffectSourceKind

from .condition_state import apply_condition
from .encounter_models.actions import CreatureRef
from .encounter_models.resolution import EncounterProgress
from .state_runtime import create_event, creature_size

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_shared_space_prone(
    state: EncounterState,
    creature_ref: CreatureRef,
    progress: EncounterProgress | None = None,
) -> bool:
    """Apply Prone when a non-exempt creature ends its turn in another's space."""

    creature_state = state.creatures[creature_ref]
    if (
        not creature_state.is_alive
        or creature_size(state, creature_ref) == "T"
        or state.effective_conditions_for(creature_ref).has(Condition.PRONE)
    ):
        return False
    co_occupants = tuple(
        other_ref
        for other_ref, other_state in state.creatures.items()
        if other_ref != creature_ref
        and other_state.is_alive
        and other_state.position == creature_state.position
    )
    if not any(
        size_rank(creature_size(state, creature_ref))
        <= size_rank(creature_size(state, other_ref))
        for other_ref in co_occupants
    ):
        return False
    result = apply_condition(
        state,
        build_applied_condition(
            condition=Condition.PRONE,
            source_ref="system:shared_space",
            source_label="Shared space",
            target_ref=creature_ref,
            source_kind=EffectSourceKind.SYSTEM,
            definition_id="shared_space_end_turn",
            origin_id=f"rule:shared-space:{creature_ref}",
        ),
    )
    if not result.accepted:
        return False
    if progress is not None:
        progress.messages.append(
            (
                "system",
                f"{creature_state.creature.name} falls prone in an occupied space.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "condition_applied",
                creature_ref=creature_ref,
                data={
                    "condition": Condition.PRONE.value,
                    "reason": "shared_space_end_turn",
                },
            )
        )
    return True
