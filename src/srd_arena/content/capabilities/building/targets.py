"""Build domain targets from authored target schemas."""

from collections.abc import Iterable
from typing import Literal, cast

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import targets
from .errors import CapabilityBuildError
from .requirements import build_checked_requirement


def build_target(
    value: object,
    *,
    content: str,
    location: str = "capability.target",
) -> domain.CapabilityTarget:
    if isinstance(value, targets.SelfTargetSchema):
        return _build_target_model(kind="self")
    if isinstance(value, targets.CreatureTargetSchema):
        return _build_target_model(
            kind="creature",
            count=domain.TargetCount(
                value.count.minimum,
                value.count.maximum,
            ),
            line_of_sight=value.line_of_sight,
            disposition=value.disposition,
            selection=value.selection,
            requirements=(
                build_checked_requirement(
                    item,
                    content=content,
                    location=f"{location}.requirements[{index}]",
                )
                for index, item in enumerate(value.requirements)
            ),
        )
    if isinstance(value, targets.AreaTargetSchema):
        chosen = value.chosen_count
        geometry = value.geometry
        return _build_target_model(
            kind="area",
            count=(
                domain.TargetCount(chosen.minimum, chosen.maximum)
                if chosen is not None
                else domain.TargetCount()
            ),
            shape=geometry.shape,
            size_feet=(
                geometry.radius_feet or geometry.length_feet or geometry.diameter_feet
            ),
            width_feet=geometry.width_feet,
            height_feet=geometry.height_feet,
            diameter_feet=geometry.diameter_feet,
            origin=value.origin,
            occupants=value.occupants,
            affects=value.affects,
            excludes_source=value.excludes_source,
            requirements=(
                build_checked_requirement(
                    item,
                    content=content,
                    location=f"{location}.requirements[{index}]",
                )
                for index, item in enumerate(value.requirements)
            ),
        )
    if isinstance(
        value,
        (targets.ActionCreatureTargetSchema, targets.ActionAreaTargetSchema),
    ):
        return _build_action_target(value, content=content, location=location)
    raise CapabilityBuildError(
        content=content,
        location=location,
        mechanic=type(value).__name__,
    )


def _build_action_target(
    value: targets.ActionTargetSchema,
    *,
    content: str,
    location: str,
) -> domain.CapabilityTarget:
    count = getattr(value, "count", 1)
    affects = getattr(value, "affects", "creatures")
    affected_kinds = (
        "objects"
        if affects == "objects"
        else "all"
        if affects == "all"
        else "creatures"
    )
    return _build_target_model(
        kind=value.type,
        count=domain.TargetCount(maximum=count),
        range_feet=getattr(value, "range_feet", None),
        shape=getattr(value, "shape", None),
        size_feet=getattr(value, "size_feet", None),
        width_feet=getattr(value, "width_feet", None),
        origin=getattr(value, "origin", "self"),
        line_of_sight=getattr(value, "line_of_sight", False),
        occupants=cast(
            Literal["all", "allies", "enemies", "chosen"],
            affects if affects in {"allies", "enemies"} else "all",
        ),
        affects=cast(
            Literal["creatures", "objects", "creatures_and_objects", "all"],
            affected_kinds,
        ),
        excludes_source=getattr(value, "excludes_self", False),
        requirements=(
            build_checked_requirement(
                requirement,
                content=content,
                location=f"{location}.requirements[{index}]",
            )
            for index, requirement in enumerate(getattr(value, "requirements", ()))
        ),
    )


def _build_target_model(
    *,
    kind: Literal["self", "creature", "area"],
    count: domain.TargetCount = domain.TargetCount(),
    range_feet: int | None = None,
    shape: str | None = None,
    size_feet: int | None = None,
    width_feet: int | None = None,
    height_feet: int | None = None,
    diameter_feet: int | None = None,
    origin: str = "self",
    line_of_sight: bool = False,
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any",
    selection: Literal["all", "choose", "choose_up_to"] = "choose",
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all",
    affects: Literal["creatures", "objects", "creatures_and_objects", "all"] = (
        "creatures"
    ),
    excludes_source: bool = False,
    requirements: Iterable[domain.CapabilityRequirement] = (),
) -> domain.CapabilityTarget:
    return domain.CapabilityTarget(
        kind=kind,
        count=count,
        range_feet=range_feet,
        shape=shape,
        size_feet=size_feet,
        width_feet=width_feet,
        height_feet=height_feet,
        diameter_feet=diameter_feet,
        origin=origin,
        line_of_sight=line_of_sight,
        disposition=disposition,
        selection=selection,
        occupants=occupants,
        affects=affects,
        excludes_source=excludes_source,
        requirements=tuple(requirements),
    )
