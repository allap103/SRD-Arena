"""Decision-local numerical candidates built only from permitted observations."""

from dataclasses import dataclass, replace

from srd_arena.engine.api import (
    AimAction,
    CastSpell,
    FilteredObservation,
    GameCommand,
    SelectAction,
    SpellCapabilityObservation,
    SpellCastOptions,
    area_aims,
)

ACTION_SCHEMA_ID = "experimental-candidates-v5"


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
    spell: SpellCapabilityObservation | None = None
    affected_refs: tuple[str, ...] | None = None
    selected_refs: tuple[str, ...] = ()
    allocations: tuple[tuple[str, int], ...] = ()
    cast_options: SpellCastOptions | None = None
    cast_complete: bool = True


def candidates(
    observation: FilteredObservation, *, maximum: int = 16384
) -> tuple[Candidate, ...]:
    """Expand advertised choices, grid-cell aims, and public resource amounts.

    Aimed actions retain every integer coordinate, annotated with disclosed
    creature coverage when area geometry is available. Fractional
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
        if action.spell_cast is not None:
            options = action.spell_cast
            aims = (
                tuple(
                    (float(x), float(y))
                    for y in range(observation.grid.height)
                    for x in range(observation.grid.width)
                )
                if action.required_configuration == "aim"
                else (None,)
            )
            coverage = {
                item.aim: item.creature_refs
                for item in area_aims(observation, action) or ()
            }
            for aim in aims:
                local = options
                if (
                    options.select_targets
                    and action.area_template is not None
                    and aim is not None
                ):
                    refs = coverage.get(aim)
                    if refs is None:
                        raise ValueError(
                            "Selective area casting requires disclosed coverage"
                        )
                    local = replace(
                        options,
                        target_refs=refs,
                        initial_target_refs=(),
                        maximum_targets=(
                            len(refs)
                            if options.maximum_is_area_count
                            else min(options.maximum_targets, len(refs))
                        ),
                    )
                refs = (
                    local.initial_target_refs
                    if local.select_targets and local.resource_pool is None
                    else ()
                )
                if len(result) >= maximum:
                    raise ValueError(f"Decision exceeds {maximum} action candidates")
                result.append(
                    Candidate(
                        CastSpell(action.id, decision, refs, (), aim),
                        *base,
                        aim=aim,
                        affected_refs=coverage.get(aim) if aim is not None else None,
                        selected_refs=refs,
                        cast_options=local,
                        cast_complete=not local.select_targets
                        or (
                            local.resource_pool is None
                            and len(refs) >= local.maximum_targets
                        ),
                    )
                )
        elif action.required_configuration == "aim":
            if observation.grid.width * observation.grid.height > maximum - len(result):
                raise ValueError(f"Decision exceeds {maximum} action candidates")
            aimed_coverage = area_aims(observation, action)
            by_aim = {item.aim: item.creature_refs for item in aimed_coverage or ()}
            for y in range(observation.grid.height):
                for x in range(observation.grid.width):
                    aim = (float(x), float(y))
                    result.append(
                        Candidate(
                            AimAction(action.id, *aim, decision),
                            *base,
                            aim=aim,
                            affected_refs=by_aim.get(aim),
                        )
                    )
        elif action.required_configuration is not None:
            raise ValueError(
                f"Unsupported action configuration: {action.required_configuration}"
            )
        else:
            result.append(Candidate(SelectAction(action.id, decision), *base))
        if len(result) > maximum:
            raise ValueError(f"Decision exceeds {maximum} action candidates")
    descriptors = {a.id: a.spell for a in observation.action_details}
    return tuple(
        replace(c, spell=descriptors.get(getattr(c.command, "action_id", "")))
        for c in result
    )
