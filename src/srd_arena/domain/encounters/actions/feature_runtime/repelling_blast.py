"""Apply the Repelling Blast invocation after successful Eldritch Blast hits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import size_rank
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    SpellResolutionDetails,
)
from srd_arena.domain.effects.triggered import matching_effects

from ...encounter_models.decisions import (
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


def resolve_repelling_blast_hits(
    state: EncounterState,
    *,
    caster: Creature,
    spell: Spell,
    caster_ref: str,
    action_id: str,
    result: ActionResolutionResult,
    progress: EncounterProgress,
) -> None:
    """Queue or automatically resolve one optional push for every qualifying hit."""

    details = result.details
    if not isinstance(details, SpellResolutionDetails):
        return
    feature = next(
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
    if feature is None:
        return
    distance = feature.parameters.get("distance_feet")
    maximum_size = feature.parameters.get("maximum_target_size")
    if not isinstance(distance, int) or not isinstance(maximum_size, str):
        return

    requests = tuple(
        ForcedMovementChoiceRequest(
            action_id=action_id,
            source_ref=caster_ref,
            target_ref=target_ref,
            direction="away",
            maximum_distance_feet=distance,
            source_id=feature.id,
            source_label="Repelling Blast",
            occurrence_index=index,
        )
        for index, attack in enumerate(details.attack_roll_details, start=1)
        if attack.get("hit") is True
        and isinstance((target_ref := attack.get("target_ref")), str)
        and size_rank(state.creatures[target_ref].creature.size)
        <= size_rank(maximum_size)
        and forced_movement_path(
            state,
            caster_ref,
            target_ref,
            "away",
            int(state.definition.grid.distance_from_feet(distance)),
        )
    )
    if not requests:
        return
    if creature_controller(state, caster_ref) == "scripted":
        for request in requests:
            maximum_steps = int(
                state.definition.grid.distance_from_feet(request.maximum_distance_feet)
            )
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
                        f"Repelling Blast pushes "
                        f"{state.creatures[request.target_ref].creature.name} "
                        f"{state.definition.grid.feet_for_squares(movement.moved_steps)} "
                        "feet away.",
                    )
                )
        return

    parent = state.current_decision()
    frames = tuple(
        DecisionFrame(
            id=next_frame_id(state, prefix="forced_movement"),
            creature_ref=caster_ref,
            kind="forced_movement",
            reason=feature.id,
            parent_frame_id=parent.id,
            parent_action_id=action_id,
            can_pass=True,
            request=request,
        )
        for request in requests
    )
    state.interrupts.decision_stack.extend(reversed(frames))
    for frame in frames:
        frame_request = frame.request
        assert isinstance(frame_request, ForcedMovementChoiceRequest)
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
                    "target_ref": frame_request.target_ref,
                    "maximum_distance_feet": frame_request.maximum_distance_feet,
                    "occurrence_index": frame_request.occurrence_index,
                },
            )
        )
    progress.paused_for_decision = True
