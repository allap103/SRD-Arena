"""Derive runtime targeting behavior from spell metadata and capabilities."""

from ..geometry import Grid
from .definitions import Spell


def spell_targets_self_only(spell: Spell) -> bool:
    """Return whether the caster is the spell's only legal target.

    >>> from .metadata import SpellRange, SpellRangeDistance
    >>> spell_targets_self_only(
    ...     Spell(
    ...         "shield", "Shield", "XPHB", 1,
    ...         range=SpellRange("point", SpellRangeDistance("self")),
    ...     )
    ... )
    True
    """

    return (
        spell.definition is not None and spell.definition.target.kind == "self"
    ) or bool(spell.range is not None and spell.range.distance.kind == "self")


def spell_chooses_area_targets(spell: Spell) -> bool:
    """Return whether an area affects selected rather than all occupants.

    >>> from ..capabilities import AutomaticResolution, CapabilityDefinition
    >>> from ..capabilities import CapabilityTarget, Outcome
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("area", occupants="chosen"),
    ...     AutomaticResolution(Outcome()),
    ... )
    >>> spell_chooses_area_targets(
    ...     Spell("storm", "Storm", "TEST", 1, definition=definition)
    ... )
    True
    """

    if spell.definition is None:
        return False
    target = spell.definition.target
    return target.kind == "area" and target.occupants == "chosen"


def spell_target_disposition(spell: Spell) -> str:
    """Return the ally, enemy, willing, or unrestricted target relationship.

    >>> from ..capabilities import AutomaticResolution, CapabilityDefinition
    >>> from ..capabilities import CapabilityTarget, Outcome
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature", disposition="ally"),
    ...     AutomaticResolution(Outcome()),
    ... )
    >>> spell_target_disposition(
    ...     Spell("aid", "Aid", "XPHB", 2, definition=definition)
    ... )
    'ally'
    """

    if spell.definition is not None and spell.definition.target.kind == "creature":
        return spell.definition.target.disposition
    return "enemy"


def spell_area_shape(spell: Spell) -> str | None:
    """Return the capability's geometric area shape, if it has one.

    >>> from ..capabilities import AutomaticResolution, CapabilityDefinition
    >>> from ..capabilities import CapabilityTarget, Outcome
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("area", shape="cone"),
    ...     AutomaticResolution(Outcome()),
    ... )
    >>> spell_area_shape(
    ...     Spell("cone", "Cone", "TEST", 1, definition=definition)
    ... )
    'cone'
    """

    if spell.definition is not None and spell.definition.target.kind == "area":
        return spell.definition.target.shape
    return None


def spell_repeats_target_allocations(spell: Spell) -> bool:
    """Return whether repeated effects may be assigned to the same target.

    >>> from ..capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityRepetition,
    ...     CapabilityTarget, Outcome,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome()),
    ...     repetition=CapabilityRepetition(3, "same_or_different"),
    ... )
    >>> spell_repeats_target_allocations(
    ...     Spell("rays", "Rays", "TEST", 2, definition=definition)
    ... )
    True
    """

    if spell.definition is not None and spell.definition.repetition is not None:
        return spell.definition.repetition.allocation in {
            "same_target",
            "same_or_different",
        }
    return False


def spell_requires_full_target_count(spell: Spell) -> bool:
    """Return whether every repeated effect must be allocated before casting.

    >>> from ..capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityRepetition,
    ...     CapabilityTarget, Outcome,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome()),
    ...     repetition=CapabilityRepetition(2),
    ... )
    >>> spell_requires_full_target_count(
    ...     Spell("rays", "Rays", "TEST", 2, definition=definition)
    ... )
    True
    """

    return bool(
        spell.definition is not None and spell.definition.repetition is not None
    )


def spell_range_squares(spell: Spell, grid: Grid) -> int | None:
    """Convert authored spell range into the encounter grid's square metric.

    >>> from .metadata import SpellRange, SpellRangeDistance
    >>> spell = Spell(
    ...     "fire_bolt", "Fire Bolt", "XPHB", 0,
    ...     range=SpellRange("point", SpellRangeDistance("feet", 120)),
    ... )
    >>> spell_range_squares(spell, Grid(20, 20))
    24
    """

    if spell.range is None:
        return None
    distance = spell.range.distance
    if distance.kind == "touch":
        return 1
    if distance.amount is None:
        return None
    amount_feet = (
        distance.amount * 5_280 if distance.kind == "miles" else distance.amount
    )
    return int(grid.distance_from_feet(amount_feet, minimum=1))


def spell_max_targets(
    spell: Spell,
    cast_level: int | None,
    *,
    caster_level: int | None = None,
) -> int:
    """Resolve target or projectile count after actor-level and slot scaling.

    >>> from ..capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityRepetition,
    ...     CapabilityScaling, CapabilityTarget, Outcome, ScalingIncrement,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome()),
    ...     repetition=CapabilityRepetition(3),
    ...     scaling=(CapabilityScaling("resource_level", per_level=(
    ...         ScalingIncrement("projectile_count", 1),
    ...     )),),
    ... )
    >>> spell = Spell(
    ...     "scorching_ray", "Scorching Ray", "XPHB", 2, definition=definition
    ... )
    >>> spell_max_targets(spell, 4)
    5
    """

    if spell.definition is not None:
        definition = spell.definition
        target_maximum = definition.target.count.maximum
        base_target_count = target_maximum if isinstance(target_maximum, int) else 1
        if definition.repetition is not None and isinstance(
            definition.repetition.count, int
        ):
            base_target_count = definition.repetition.count
        if caster_level is not None:
            actor_thresholds = sorted(
                (
                    threshold
                    for scaling in definition.scaling
                    if scaling.basis == "actor_level"
                    for threshold in scaling.thresholds
                    if threshold.minimum_level <= caster_level
                    and any(
                        increment.kind in {"target_count", "projectile_count"}
                        and isinstance(increment.amount, int)
                        for increment in threshold.increments
                    )
                ),
                key=lambda threshold: threshold.minimum_level,
            )
            if actor_thresholds:
                base_target_count = next(
                    increment.amount
                    for increment in actor_thresholds[-1].increments
                    if increment.kind in {"target_count", "projectile_count"}
                    and isinstance(increment.amount, int)
                )
        resolved_level = cast_level if cast_level is not None else spell.level
        levels_above = max(0, resolved_level - spell.level)
        per_level_increment = sum(
            increment.amount
            for scaling in definition.scaling
            if scaling.basis == "resource_level"
            for increment in scaling.per_level
            if increment.kind in {"target_count", "projectile_count"}
            and isinstance(increment.amount, int)
        )
        return base_target_count + levels_above * per_level_increment
    return 1
