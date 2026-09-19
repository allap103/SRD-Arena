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
    allied_creature_refs: frozenset[str] = frozenset(),
) -> tuple[ActionObservation, ...]:
    """Return choices whose availability contains only player-known facts."""

    projected: list[ActionObservation] = []
    for action in actions:
        if (
            action.creature_ref not in allied_creature_refs
            and action.spell_cast is not None
        ):
            action = replace(action, spell_cast=None)
        if action.spell_cast is not None:
            config = action.spell_cast
            action = replace(
                action,
                spell_cast=replace(
                    config,
                    target_refs=tuple(
                        r for r in config.target_refs if r in visible_creature_refs
                    ),
                    initial_target_refs=tuple(
                        r
                        for r in config.initial_target_refs
                        if r in visible_creature_refs
                    ),
                    resource_limits=tuple(
                        (r, n)
                        for r, n in config.resource_limits
                        if r in allied_creature_refs
                    ),
                ),
            )
        if (
            action.spell_cast is not None
            and action.spell_cast.resource_pool is not None
        ):
            config = action.spell_cast
            action = replace(
                action,
                spell_cast=replace(
                    config,
                    maximum_targets=len(config.resource_limits),
                    target_refs=tuple(
                        r for r in config.target_refs if r in allied_creature_refs
                    ),
                    initial_target_refs=tuple(
                        r
                        for r in config.initial_target_refs
                        if r in allied_creature_refs
                    ),
                ),
            )
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
