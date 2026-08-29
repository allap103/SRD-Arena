"""Report capability semantics the encounter runtime cannot execute faithfully.

The capability model intentionally preserves more authored meaning than the
current encounter runtime implements. This module is the explicit boundary
between those two concerns: definitions remain lossless, while action
eligibility rejects combinations that would otherwise run with different
semantics.

Line-of-sight declarations need no rejection yet because the current spatial
model has no opaque terrain or hidden entities; every represented target is
visible by construction. That invariant should be replaced by a rule query
when visibility enters the encounter model.
"""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.domain.capabilities import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityResolution,
    CapabilityTarget,
    EffectDuration,
    SavingThrowResolution,
)


@dataclass(frozen=True)
class CapabilityRuntimeIssue:
    """Explain one authored semantic that cannot yet execute faithfully."""

    code: str
    message: str


def capability_runtime_issue(
    definition: CapabilityDefinition,
    *,
    supports_turn_relative_durations: bool = False,
) -> CapabilityRuntimeIssue | None:
    """Return the first unsupported semantic reachable from a definition.

    The traversal includes follow-up targets, trigger resolutions, repeated
    save effects, and their automatic ending durations. This prevents nested
    mechanics from bypassing the same support boundary as the primary outcome.

    >>> from srd_arena.domain.capabilities import AutomaticResolution, Outcome
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("area", affected_entities="objects"),
    ...     AutomaticResolution(Outcome()),
    ... )
    >>> capability_runtime_issue(definition).code
    'unsupported_target_entities'
    """

    for target in (
        definition.target,
        *(step.target for step in definition.follow_ups),
    ):
        issue = capability_target_runtime_issue(target)
        if issue is not None:
            return issue
    for resolution in (
        definition.resolution,
        *(trigger.resolution for trigger in definition.triggers),
        *(step.resolution for step in definition.follow_ups),
    ):
        issue = _resolution_runtime_issue(
            resolution,
            supports_turn_relative_durations=supports_turn_relative_durations,
        )
        if issue is not None:
            return issue
    return None


def capability_target_runtime_issue(
    target: CapabilityTarget,
) -> CapabilityRuntimeIssue | None:
    """Return why a target declaration cannot execute without information loss.

    >>> capability_target_runtime_issue(
    ...     CapabilityTarget("area", occupants="enemies")
    ... ).code
    'unsupported_area_occupants'
    >>> capability_target_runtime_issue(CapabilityTarget("creature")) is None
    True
    """

    if target.affected_entities != "creatures":
        return CapabilityRuntimeIssue(
            "unsupported_target_entities",
            "Areas that affect objects are not executable yet.",
        )
    if target.kind == "area" and target.occupants in {"allies", "enemies"}:
        return CapabilityRuntimeIssue(
            "unsupported_area_occupants",
            "Area occupant filters for allies or enemies are not executable yet.",
        )
    if target.kind == "area" and target.excludes_source and target.origin != "self":
        return CapabilityRuntimeIssue(
            "unsupported_source_exclusion",
            "Explicitly excluding the source from a point area is not executable yet.",
        )
    if target.kind == "creature" and target.count.minimum > 1:
        return CapabilityRuntimeIssue(
            "unsupported_target_minimum",
            "Creature target minimums greater than one are not executable yet.",
        )
    if (
        target.kind == "creature"
        and target.selection in {"all", "choose"}
        and target.count.maximum != 1
    ):
        return CapabilityRuntimeIssue(
            "unsupported_exact_target_count",
            "Exact or all-creature target sets are not executable yet.",
        )
    return None


def effect_duration_runtime_issue(
    duration: EffectDuration | None,
    *,
    supports_turn_relative_durations: bool = False,
) -> CapabilityRuntimeIssue | None:
    """Return why an effect duration cannot execute with its authored ending.

    >>> issue = effect_duration_runtime_issue(
    ...     EffectDuration("until_event", events=("hit", "save"), event_match="all")
    ... )
    >>> (issue.code, issue.message)
    ('unsupported_all_event_duration', 'Effects that end only after all listed events are not executable yet.')
    """

    if duration is None or duration.kind == "timed":
        return None
    if duration.kind in {"start_of_turn", "end_of_turn"}:
        if supports_turn_relative_durations or (
            duration.creature == "source" and duration.turn_offset == 1
        ):
            return None
        return CapabilityRuntimeIssue(
            "unsupported_turn_relative_duration",
            "Only next-source-turn effect durations are executable for spells yet.",
        )
    if duration.kind == "permanent":
        return CapabilityRuntimeIssue(
            "unsupported_permanent_effect_duration",
            "Permanent effect durations are not executable yet.",
        )
    if duration.kind != "until_event":
        return CapabilityRuntimeIssue(
            "unsupported_effect_duration",
            f"Effect duration '{duration.kind}' is not executable yet.",
        )
    if duration.event_match == "all" and len(duration.events) > 1:
        return CapabilityRuntimeIssue(
            "unsupported_all_event_duration",
            "Effects that end only after all listed events are not executable yet.",
        )
    return CapabilityRuntimeIssue(
        "unsupported_event_duration",
        "Event-ended effect durations are not executable yet.",
    )


def _resolution_runtime_issue(
    resolution: CapabilityResolution,
    *,
    supports_turn_relative_durations: bool,
) -> CapabilityRuntimeIssue | None:
    if isinstance(resolution, AutomaticResolution):
        return _effects_runtime_issue(
            resolution.outcome.effects,
            supports_turn_relative_durations=supports_turn_relative_durations,
        )
    if isinstance(resolution, AttackResolution):
        return _effects_runtime_issue(
            (*resolution.hit.effects, *resolution.miss.effects),
            supports_turn_relative_durations=supports_turn_relative_durations,
        )
    if isinstance(resolution, SavingThrowResolution):
        for stage in resolution.failure:
            issue = _effects_runtime_issue(
                stage.effects,
                supports_turn_relative_durations=supports_turn_relative_durations,
            )
            if issue is not None:
                return issue
            for repeat_save in stage.repeat_saves:
                issue = effect_duration_runtime_issue(
                    repeat_save.automatic_success_after,
                    supports_turn_relative_durations=supports_turn_relative_durations,
                ) or _effects_runtime_issue(
                    repeat_save.failure_effects,
                    supports_turn_relative_durations=supports_turn_relative_durations,
                )
                if issue is not None:
                    return issue
        return _effects_runtime_issue(
            (*resolution.success.effects, *resolution.always.effects),
            supports_turn_relative_durations=supports_turn_relative_durations,
        )
    return None


def _effects_runtime_issue(
    effects: tuple[CapabilityEffect, ...],
    *,
    supports_turn_relative_durations: bool,
) -> CapabilityRuntimeIssue | None:
    for effect in effects:
        duration = getattr(effect, "duration", None)
        if isinstance(duration, EffectDuration):
            issue = effect_duration_runtime_issue(
                duration,
                supports_turn_relative_durations=supports_turn_relative_durations,
            )
            if issue is not None:
                return issue
    return None
