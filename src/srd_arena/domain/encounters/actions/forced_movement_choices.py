"""Expose optional forced movement through ordinary typed encounter decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..encounter_models.actions import EncounterAction, ForcedMovementSelection
from ..encounter_models.decisions import (
    DecisionFrame,
    ForcedMovementChoiceRequest,
)
from ..encounter_models.resolution import DecisionExecutionResult, EncounterProgress
from ..forced_movement import (
    ForcedMovementResult,
    apply_forced_movement,
    forced_movement_path,
)
from ..state_runtime import create_event, creature_label

if TYPE_CHECKING:
    from ..encounter import EncounterState


def forced_movement_request(
    decision: DecisionFrame,
) -> ForcedMovementChoiceRequest:
    """Return the typed forced-movement request carried by a decision frame."""

    if not isinstance(decision.request, ForcedMovementChoiceRequest):
        raise TypeError(
            "Forced movement decision requires a ForcedMovementChoiceRequest."
        )
    return decision.request


def forced_movement_actions(state: EncounterState) -> list[EncounterAction]:
    """Offer decline and each currently reachable distance for an optional move."""

    decision = state.current_decision()
    request = forced_movement_request(decision)
    maximum_steps = _maximum_steps(state, request)
    actions = [
        EncounterAction(
            f"Do not use {request.source_label}",
            "forced_movement_choice",
            ForcedMovementSelection(
                request.target_ref,
                request.direction,
                0,
            ),
            id=(
                f"{request.action_id}-{request.source_id}-"
                f"{request.occurrence_index}-push-0"
            ),
            creature_ref=request.source_ref,
            source_trigger_id=request.source_id,
        )
    ]
    actions.extend(
        EncounterAction(
            f"{'Push' if request.direction == 'away' else 'Pull'} "
            f"{creature_label(state, request.target_ref)} "
            f"{state.definition.grid.feet_for_squares(steps)} ft.",
            "forced_movement_choice",
            ForcedMovementSelection(
                request.target_ref,
                request.direction,
                state.definition.grid.feet_for_squares(steps),
            ),
            id=(
                f"{request.action_id}-{request.source_id}-"
                f"{request.occurrence_index}-push-{steps}"
            ),
            creature_ref=request.source_ref,
            source_trigger_id=request.source_id,
        )
        for steps in range(1, maximum_steps + 1)
    )
    return actions


def apply_forced_movement_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> DecisionExecutionResult:
    """Resolve one advertised forced-movement distance and close its decision."""

    request = forced_movement_request(decision)
    selection = action.value
    if action.kind != "forced_movement_choice" or not isinstance(
        selection, ForcedMovementSelection
    ):
        raise ValueError("Forced movement requires an advertised distance choice.")
    if (
        selection.target_ref != request.target_ref
        or selection.direction != request.direction
    ):
        raise ValueError("Forced movement choice does not match its request.")
    if selection.distance_feet < 0:
        raise ValueError("Forced movement distance cannot be negative.")
    steps = int(state.definition.grid.distance_from_feet(selection.distance_feet))
    if state.definition.grid.feet_for_squares(steps) != selection.distance_feet:
        raise ValueError("Forced movement distance must use whole grid cells.")
    if steps < 0 or steps > _maximum_steps(state, request):
        raise ValueError("Forced movement distance is no longer available.")
    progress = EncounterProgress()
    result = resolve_forced_movement_request(
        state,
        request,
        steps,
        progress,
        frame_id=decision.id,
    )
    _record_result_message(state, request, result, progress)
    return DecisionExecutionResult(progress, action.id, completed=True)


def resolve_forced_movement_request(
    state: EncounterState,
    request: ForcedMovementChoiceRequest,
    steps: int,
    progress: EncounterProgress,
    *,
    frame_id: str | None = None,
) -> ForcedMovementResult:
    """Apply a chosen distance and publish a structured movement event."""

    result = apply_forced_movement(
        state,
        request.source_ref,
        request.target_ref,
        request.direction,
        steps,
    )
    progress.events.append(
        create_event(
            state,
            "forced_movement_resolved",
            creature_ref=request.source_ref,
            frame_id=frame_id,
            action_id=request.action_id,
            data={
                "source_id": request.source_id,
                "source_label": request.source_label,
                "target_ref": request.target_ref,
                "direction": request.direction,
                "occurrence_index": request.occurrence_index,
                "requested_distance_feet": state.definition.grid.feet_for_squares(
                    steps
                ),
                "moved_distance_feet": state.definition.grid.feet_for_squares(
                    result.moved_steps
                ),
                "path": [
                    {"x": position.x, "y": position.y} for position in result.path
                ],
                "blocked": result.blocked,
                "ended_grapples": [
                    {"source_ref": source_ref, "target_ref": target_ref}
                    for source_ref, target_ref in result.ended_grapples
                ],
            },
        )
    )
    return result


def _maximum_steps(
    state: EncounterState,
    request: ForcedMovementChoiceRequest,
) -> int:
    allowed = int(
        state.definition.grid.distance_from_feet(request.maximum_distance_feet)
    )
    return len(
        forced_movement_path(
            state,
            request.source_ref,
            request.target_ref,
            request.direction,
            allowed,
        )
    )


def _record_result_message(
    state: EncounterState,
    request: ForcedMovementChoiceRequest,
    result: ForcedMovementResult,
    progress: EncounterProgress,
) -> None:
    target_label = creature_label(state, request.target_ref)
    if result.moved_steps == 0:
        progress.messages.append(
            ("system", f"{request.source_label} does not move {target_label}.")
        )
        return
    distance = state.definition.grid.feet_for_squares(result.moved_steps)
    progress.messages.append(
        (
            "system",
            f"{request.source_label} moves {target_label} {distance} feet "
            f"{request.direction}.",
        )
    )
