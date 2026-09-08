"""Keep hidden occupancy out of advertised movement availability."""

from dataclasses import replace

from srd_arena.domain.encounters.actions.eligibility_rules.common import MovementRule
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction

from .observation_models import ActionObservation


def player_movement_observations(
    actions: tuple[ActionObservation, ...],
    state: EncounterState,
    visible_creature_refs: frozenset[str],
) -> tuple[ActionObservation, ...]:
    """Retest blocked moves using known occupants, preserving all other failures.

    This only changes advertised availability. Execution uses the unchanged
    encounter and therefore cannot move into an unseen creature's footprint.
    """

    hidden = frozenset(state.creatures) - visible_creature_refs
    if not hidden:
        return actions
    projected: list[ActionObservation] = []
    for action in actions:
        if (
            action.kind != "move"
            or action.availability == "unimplemented"
            or not any(
                reason.code == "destination_blocked" for reason in action.reasons
            )
        ):
            projected.append(action)
            continue
        failure = MovementRule().check(
            state,
            action.creature_ref,
            EncounterAction(
                action.label,
                "move",
                value=action.movement_direction,
                creature_ref=action.creature_ref,
            ),
            ignored_occupants=hidden,
        )
        if failure is not None:
            projected.append(action)
            continue
        reasons = tuple(
            reason for reason in action.reasons if reason.code != "destination_blocked"
        )
        projected.append(
            replace(
                action,
                reasons=reasons,
                enabled=not reasons,
                availability="unavailable" if reasons else "available",
            )
        )
    return tuple(projected)
