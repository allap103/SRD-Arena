"""Apply the Repelling Blast invocation after one Eldritch Blast hit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import size_rank
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    SpellResolutionDetails,
)
from srd_arena.domain.effects.triggered import TriggeredEffect, matching_effects

from ...encounter_models.decisions import (
    DecisionContinuation,
    DecisionFrame,
    ForcedMovementChoiceRequest,
)
from ...encounter_models.resolution import EncounterProgress
from ...forced_movement import forced_movement_path
from ...participants import creature_controller
from ...state_runtime import create_event, next_frame_id
from ..forced_movement_choices import resolve_forced_movement_request

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature
    from srd_arena.domain.spells import Spell

    from ...encounter import EncounterState


def repelling_blast_effect(
    caster: Creature,
    spell: Spell,
) -> TriggeredEffect | None:
    """Return the caster's Repelling Blast binding for this spell, if present."""

    return next(
        (
            effect
            for effect in matching_effects(
                caster.triggered_effects,
                "spell_attack_hit",
                {"spell_id": spell.id},
            )
            if effect.id == "repelling_blast" and effect.operation == "push_away"
        ),
        None,
    )


def resolve_repelling_blast_hit(
    state: EncounterState,
    *,
    caster: Creature,
    spell: Spell,
    caster_ref: str,
    action_id: str,
    result: ActionResolutionResult,
    progress: EncounterProgress,
    continuation: DecisionContinuation | None = None,
) -> bool:
    """Resolve or open the optional push for one completed projectile hit.

    Return ``True`` only when an external controller must answer the newly
    opened decision before the supplied continuation can resume.
    """

    details = result.details
    feature = repelling_blast_effect(caster, spell)
    if not isinstance(details, SpellResolutionDetails) or feature is None:
        return False
    distance = feature.parameters.get("distance_feet")
    maximum_size = feature.parameters.get("maximum_target_size")
    if not isinstance(distance, int) or not isinstance(maximum_size, str):
        return False
    attack = next(
        (detail for detail in details.attack_roll_details if detail.get("hit") is True),
        None,
    )
    if attack is None:
        return False
    target_ref = attack.get("target_ref")
    if not isinstance(target_ref, str):
        return False
    target_state = state.creatures.get(target_ref)
    if target_state is None or size_rank(target_state.creature.size) > size_rank(
        maximum_size
    ):
        return False
    maximum_steps = int(state.definition.grid.distance_from_feet(distance))
    if not forced_movement_path(
        state,
        caster_ref,
        target_ref,
        "away",
        maximum_steps,
    ):
        return False
    projectile_index = attack.get("projectile_index")
    request = ForcedMovementChoiceRequest(
        action_id=action_id,
        source_ref=caster_ref,
        target_ref=target_ref,
        direction="away",
        maximum_distance_feet=distance,
        source_id=feature.id,
        source_label="Repelling Blast",
        occurrence_index=(projectile_index if isinstance(projectile_index, int) else 1),
    )
    if creature_controller(state, caster_ref) == "scripted":
        movement = resolve_forced_movement_request(
            state,
            request,
            maximum_steps,
            progress,
        )
        if movement.moved_steps:
            progress.messages.append(
                (
                    "system",
                    f"Repelling Blast pushes {target_state.creature.name} "
                    f"{state.definition.grid.feet_for_squares(movement.moved_steps)} "
                    "feet away.",
                )
            )
        return False

    parent = state.current_decision()
    frame = DecisionFrame(
        id=next_frame_id(state, prefix="forced_movement"),
        creature_ref=caster_ref,
        kind="forced_movement",
        reason=feature.id,
        parent_frame_id=parent.id,
        parent_action_id=action_id,
        can_pass=True,
        request=request,
        continuation=continuation,
    )
    state.interrupts.decision_stack.append(frame)
    progress.events.append(
        create_event(
            state,
            "decision_opened",
            creature_ref=caster_ref,
            frame_id=frame.id,
            action_id=action_id,
            data={
                "kind": "forced_movement",
                "source_id": feature.id,
                "target_ref": target_ref,
                "maximum_distance_feet": distance,
                "occurrence_index": request.occurrence_index,
            },
        )
    )
    progress.paused_for_decision = True
    return True
