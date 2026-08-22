"""Orchestrate construction of complete domain capabilities."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Literal, Protocol, cast

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import resolutions, scaling
from .common import resolution_root
from .errors import CapabilityBuildError
from .requirements import build_checked_requirement
from .resolutions import build_resolution
from .scaling import build_scaling_rules
from .targets import build_target


class _RepetitionLike(Protocol):
    count: int | Literal["ability_modifier", "resource_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ]
    simultaneous: bool
    propagation_range_feet: int | None
    cannot_repeat_target: bool


class _TriggerLike(Protocol):
    event: str
    resolution: object
    requirements: Sequence[object]


class _SequenceStepLike(Protocol):
    target: object | None
    resolution: object


class _SequenceLike(Protocol):
    steps: Sequence[_SequenceStepLike]


def build_capability(
    *,
    target: object,
    resolution: object,
    content: str,
    condition_selection: Literal["all", "choose_one"] = "all",
    scaling_rules: Iterable[scaling.CapabilityScalingSchema] = (),
    triggers: Iterable[object] = (),
    location: str = "capability.resolution",
) -> domain.CapabilityDefinition:
    """Build the executable subset of the shared capability vocabulary.

    Source packages may add non-executable authoring schemas, but executable
    targets, resolutions, effects, requirements, repetition, and scaling all
    converge here. Unsupported structured mechanics fail with their authored
    location instead of being silently omitted.
    """
    outer_resolution = resolution_root(resolution)
    sequence = (
        outer_resolution
        if isinstance(outer_resolution, resolutions.SequenceResolutionSchemaBase)
        else None
    )
    primary_resolution = outer_resolution
    primary_location = location
    if sequence is not None:
        steps = tuple(getattr(sequence, "steps", ()))
        if not steps:
            raise CapabilityBuildError(
                content=content,
                location=f"{location}.steps",
                mechanic="empty sequence",
            )
        primary_resolution = resolution_root(steps[0].resolution)
        primary_location += ".steps[0].resolution"
    repeated = (
        primary_resolution
        if isinstance(primary_resolution, resolutions.RepeatResolutionSchemaBase)
        else None
    )
    if repeated is not None:
        primary_resolution = resolution_root(getattr(repeated, "resolution", None))
        primary_location += ".resolution"

    definition = domain.CapabilityDefinition(
        target=build_target(target, content=content),
        resolution=build_resolution(
            primary_resolution,
            content=content,
            location=primary_location,
        ),
        condition_selection=condition_selection,
    )
    return replace(
        definition,
        repetition=_build_repetition(repeated),
        scaling=build_scaling_rules(scaling_rules),
        triggers=_build_triggers(target, triggers, content=content),
        follow_ups=_build_follow_ups(
            target,
            sequence,
            content=content,
            location=location,
        ),
    )


def _build_repetition(value: object | None) -> domain.CapabilityRepetition | None:
    if value is None:
        return None
    repetition = cast(_RepetitionLike, value)
    return domain.CapabilityRepetition(
        count=repetition.count,
        allocation=repetition.allocation,
        simultaneous=repetition.simultaneous,
        propagation_range_feet=repetition.propagation_range_feet,
        cannot_repeat_target=repetition.cannot_repeat_target,
    )


def _build_triggers(
    target: object,
    values: Iterable[object],
    *,
    content: str,
) -> tuple[domain.CapabilityTrigger, ...]:
    built: list[domain.CapabilityTrigger] = []
    for index, raw_value in enumerate(values):
        value = cast(_TriggerLike, raw_value)
        location = f"capability.outcome_triggers[{index}].resolution"
        nested = build_capability(
            target=target,
            resolution=value.resolution,
            content=content,
            location=location,
        )
        built.append(
            domain.CapabilityTrigger(
                event=value.event,
                resolution=nested.resolution,
                requirements=tuple(
                    build_checked_requirement(
                        item,
                        content=content,
                        location=location,
                    )
                    for item in value.requirements
                ),
            )
        )
    return tuple(built)


def _build_follow_ups(
    target: object,
    sequence: object | None,
    *,
    content: str,
    location: str,
) -> tuple[domain.CapabilityStep, ...]:
    if sequence is None:
        return ()
    authored_sequence = cast(_SequenceLike, sequence)
    built: list[domain.CapabilityStep] = []
    for index, step in enumerate(tuple(authored_sequence.steps)[1:], start=1):
        nested = build_capability(
            target=step.target or target,
            resolution=step.resolution,
            content=content,
            location=f"{location}.steps[{index}].resolution",
        )
        built.append(domain.CapabilityStep(nested.target, nested.resolution))
    return tuple(built)
