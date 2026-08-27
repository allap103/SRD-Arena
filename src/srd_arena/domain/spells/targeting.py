"""Provide targeting support for the spells package."""

from ..geometry import Grid
from .definitions import Spell


def spell_targets_self_only(spell: Spell) -> bool:
    """Handle spell targets self only."""

    return (
        spell.definition is not None and spell.definition.target.kind == "self"
    ) or spell.range_data.get("type") == "self"


def spell_chooses_area_targets(spell: Spell) -> bool:
    """Handle spell chooses area targets."""

    if spell.definition is None:
        return False
    target = spell.definition.target
    return target.kind == "area" and target.occupants == "chosen"


def spell_target_disposition(spell: Spell) -> str:
    """Handle spell target disposition."""

    if spell.definition is not None and spell.definition.target.kind == "creature":
        return spell.definition.target.disposition
    return "enemy"


def spell_area_shape(spell: Spell) -> str | None:
    """Handle spell area shape."""

    if spell.definition is not None and spell.definition.target.kind == "area":
        return spell.definition.target.shape
    return None


def spell_repeats_target_allocations(spell: Spell) -> bool:
    """Handle spell repeats target allocations."""

    if spell.definition is not None and spell.definition.repetition is not None:
        return spell.definition.repetition.allocation in {
            "same_target",
            "same_or_different",
        }
    return False


def spell_requires_full_target_count(spell: Spell) -> bool:
    """Handle spell requires full target count."""

    return bool(
        spell.definition is not None and spell.definition.repetition is not None
    )


def spell_range_squares(spell: Spell, grid: Grid) -> int | None:
    """Handle spell range squares."""

    distance = spell.range_data.get("distance", {})
    if not isinstance(distance, dict):
        return None
    amount = distance.get("amount")
    if distance.get("type") == "touch":
        return 1
    if not isinstance(amount, int):
        return None
    return int(grid.distance_from_feet(amount, minimum=1))


def spell_max_targets(
    spell: Spell,
    cast_level: int | None,
    *,
    caster_level: int | None = None,
) -> int:
    """Handle spell max targets."""

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
