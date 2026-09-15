"""Decision-local numerical candidates built only from permitted observations."""

from dataclasses import dataclass

from srd_arena.engine.api import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    ConfirmTargeting,
    FilteredObservation,
    GameCommand,
    SelectAction,
    SetResourceAllocation,
)

ACTION_SCHEMA_ID = "experimental-candidates-v1"


@dataclass(frozen=True)
class Candidate:
    """Bind numerical features to a command token without encoding its ID."""

    command: GameCommand
    kind: str
    actor_ref: str
    target_ref: str | None = None
    aim: tuple[float, float] | None = None
    amount: int | None = None
    remove: bool = False


def candidates(
    observation: FilteredObservation, *, maximum: int = 16384
) -> tuple[Candidate, ...]:
    """Expand advertised choices, grid-cell aims, and public resource amounts.

    Aimed actions use cell centers in the experimental grammar. Fractional
    aiming is deliberately outside this initial discrete action space. These
    are permitted attempts, not privileged guarantees of successful execution.
    No failed-attempt pruning or private legality probes are performed.
    """
    result: list[Candidate] = []
    decision = observation.decision.id
    if observation.completion is not None:
        return ()
    for action in sorted(observation.action_details, key=lambda a: a.id):
        if not action.enabled or action.availability != "available":
            continue
        base = (action.kind, action.creature_ref, action.target_ref)
        if action.required_configuration == "aim":
            if observation.grid.width * observation.grid.height > maximum - len(result):
                raise ValueError(f"Decision exceeds {maximum} action candidates")
            for y in range(observation.grid.height):
                for x in range(observation.grid.width):
                    result.append(
                        Candidate(
                            AimAction(action.id, float(x), float(y), decision),
                            *base,
                            aim=(float(x), float(y)),
                        )
                    )
        elif action.required_configuration is not None:
            raise ValueError(
                f"Unsupported action configuration: {action.required_configuration}"
            )
        elif action.kind == "set_spell_resource_allocation":
            targeting = observation.targeting
            if targeting is None or action.target_ref is None:
                raise ValueError(
                    "Allocation action is missing public targeting metadata"
                )
            limit = next(
                (
                    x.maximum
                    for x in targeting.resource_limits
                    if x.target_ref == action.target_ref
                ),
                None,
            )
            if limit is None:
                raise ValueError(
                    "Allocation action is missing a permitted resource limit"
                )
            if limit > maximum:
                raise ValueError("Resource allocation exceeds candidate capacity")
            for amount in range(limit + 1):
                result.append(
                    Candidate(
                        SetResourceAllocation(action.target_ref, amount, decision),
                        *base,
                        amount=amount,
                    )
                )
        elif action.kind == "toggle_spell_target":
            if observation.targeting is None or action.target_ref is None:
                raise ValueError("Target action is missing targeting metadata")
            selected = action.target_ref in observation.targeting.selected_target_refs
            removes = (
                (False, True)
                if selected and observation.targeting.repeat_target_allocations
                else (selected,)
            )
            for remove in removes:
                result.append(
                    Candidate(
                        ChangeTarget(
                            action.target_ref,
                            remove,
                            decision,
                            action.source_trigger_id,
                        ),
                        *base,
                        remove=remove,
                    )
                )
        elif action.kind == "confirm_spell_targets":
            result.append(Candidate(ConfirmTargeting(decision), *base))
        elif action.kind == "cancel_spell_targets":
            result.append(Candidate(CancelTargeting(decision), *base))
        else:
            result.append(Candidate(SelectAction(action.id, decision), *base))
        if len(result) > maximum:
            raise ValueError(f"Decision exceeds {maximum} action candidates")
    return tuple(result)
