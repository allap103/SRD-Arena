from typing import cast

import pytest

from srd_arena.content.capabilities import durations, requirements, targets
from srd_arena.content.capabilities.builder import (
    build_duration,
    build_requirement,
    build_target,
)
from srd_arena.content.spells.building.targeting import (
    creature_types_from_requirements,
)
from srd_arena.content.spells.targeting import (
    AnyRequirementSchema,
    SpellRequirementSchema,
)
from srd_arena.domain.capabilities import (
    ConditionRequirement,
    CreatureTypeRequirement,
    NotAffectedRequirement,
    SizeRequirement,
)


def test_shared_target_variants_map_all_meaningful_fields() -> None:
    self_target = build_target(targets.SelfTargetSchema(type="self"))
    creature_target = build_target(
        targets.CreatureTargetSchema(
            type="creature",
            count=2,
            range_feet=30,
            line_of_sight=True,
            requirements=[
                requirements.CreatureTypeRequirementSchema(
                    type="creature_type",
                    creature_types=["humanoid"],
                )
            ],
        )
    )
    area_target = build_target(
        targets.AreaTargetSchema(
            type="area",
            shape="line",
            size_feet=60,
            width_feet=5,
            origin="point_in_range",
            range_feet=120,
            affects="enemies",
            excludes_self=False,
        )
    )
    object_area = build_target(
        targets.AreaTargetSchema(
            type="area",
            shape="cube",
            size_feet=10,
            affects="objects",
        )
    )

    assert self_target.kind == "self"
    assert (
        creature_target.kind,
        creature_target.count.maximum,
        creature_target.range_feet,
        creature_target.line_of_sight,
    ) == ("creature", 2, 30, True)
    assert creature_target.requirements == (CreatureTypeRequirement(("humanoid",)),)
    assert (
        area_target.kind,
        area_target.shape,
        area_target.size_feet,
        area_target.width_feet,
        area_target.origin,
        area_target.range_feet,
        area_target.occupants,
        area_target.excludes_source,
        area_target.affected_entities,
    ) == (
        "area",
        "line",
        60,
        5,
        "point_in_range",
        120,
        "enemies",
        False,
        "creatures",
    )
    assert object_area.affected_entities == "objects"


def test_shared_requirement_variants_map_without_default_fallbacks() -> None:
    built = (
        build_requirement(
            requirements.SizeRequirementSchema(type="size", maximum="L", minimum="S")
        ),
        build_requirement(
            requirements.ConditionRequirementSchema(
                type="condition",
                conditions=["grappled"],
                match="all",
                applied_by="source",
            )
        ),
        build_requirement(
            requirements.CreatureTypeRequirementSchema(
                type="creature_type",
                creature_types=["humanoid", "giant"],
            )
        ),
        build_requirement(
            requirements.NotAffectedRequirementSchema(
                type="not_affected_by",
                action="Vampire Bite",
            )
        ),
    )

    assert built == (
        SizeRequirement("L", "S"),
        ConditionRequirement(("grappled",), "all", "source"),
        CreatureTypeRequirement(("humanoid", "giant")),
        NotAffectedRequirement("Vampire Bite"),
    )


def test_shared_duration_variants_preserve_variant_specific_fields() -> None:
    built = (
        build_duration(
            durations.EndOfTurnDurationSchema(
                type="end_of_turn", creature="target", turn_offset=2
            )
        ),
        build_duration(
            durations.StartOfTurnDurationSchema(
                type="start_of_turn", creature="source", turn_offset=1
            )
        ),
        build_duration(
            durations.TimedDurationSchema(type="timed", amount=3, unit="round")
        ),
        build_duration(
            durations.UntilEventDurationSchema(
                type="until_event",
                events=["target_takes_damage", "adjacent_creature_wakes_target"],
                match="all",
            )
        ),
        build_duration(durations.PermanentDurationSchema(type="permanent")),
    )

    assert built[0] is not None and (
        built[0].kind,
        built[0].creature,
        built[0].turn_offset,
    ) == ("end_of_turn", "target", 2)
    assert built[1] is not None and (
        built[1].kind,
        built[1].creature,
        built[1].turn_offset,
    ) == ("start_of_turn", "source", 1)
    assert built[2] is not None and (
        built[2].kind,
        built[2].amount,
        built[2].unit,
    ) == ("timed", 3, "round")
    assert built[3] is not None and built[3].events == (
        "target_takes_damage",
        "adjacent_creature_wakes_target",
    )
    assert built[3] is not None and built[3].event_match == "all"
    assert built[4] is not None and built[4].kind == "permanent"


def test_spell_creature_type_extraction_does_not_flatten_boolean_groups() -> None:
    nested = AnyRequirementSchema(
        type="any",
        requirements=[
            requirements.ConditionRequirementSchema(
                type="condition", conditions=["charmed"]
            ),
            requirements.CreatureTypeRequirementSchema(
                type="creature_type", creature_types=["humanoid"]
            ),
        ],
    )

    direct = requirements.CreatureTypeRequirementSchema(
        type="creature_type", creature_types=["giant"]
    )

    assert creature_types_from_requirements([direct, nested]) == ("giant",)


def test_translators_reject_values_outside_their_closed_unions() -> None:
    unsupported = object()

    with pytest.raises(AssertionError):
        build_target(cast(targets.ActionTargetSchema, unsupported))
    with pytest.raises(AssertionError):
        build_requirement(cast(requirements.ActionRequirementSchema, unsupported))
    with pytest.raises(AssertionError):
        build_duration(cast(durations.EffectDurationSchema, unsupported))
    with pytest.raises(AssertionError):
        creature_types_from_requirements([cast(SpellRequirementSchema, unsupported)])
