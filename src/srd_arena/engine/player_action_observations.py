"""Project engine action options without disclosing private target facts."""

from dataclasses import replace

from .observation_models import ActionObservation

_PRIVATE_TARGET_FAILURE_CODES = frozenset(
    {"target_condition_required", "target_creature_type_required"}
)


def player_action_observations(
    actions: tuple[ActionObservation, ...],
    *,
    visible_creature_refs: frozenset[str],
) -> tuple[ActionObservation, ...]:
    """Return choices whose availability contains only player-known facts."""

    projected: list[ActionObservation] = []
    for action in actions:
        if (
            action.target_ref is not None
            and action.target_ref not in visible_creature_refs
        ):
            continue
        if action.target_ref is None or action.availability == "unimplemented":
            projected.append(action)
            continue
        public_reasons = tuple(
            reason
            for reason in action.reasons
            if reason.code not in _PRIVATE_TARGET_FAILURE_CODES
        )
        if public_reasons == action.reasons:
            projected.append(action)
            continue
        enabled = not public_reasons
        projected.append(
            replace(
                action,
                enabled=enabled,
                availability="available" if enabled else "unavailable",
                reasons=public_reasons,
            )
        )
    return tuple(projected)
