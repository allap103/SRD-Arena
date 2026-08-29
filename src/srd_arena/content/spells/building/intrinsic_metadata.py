"""Translate authored intrinsic spell metadata into immutable domain values."""

from collections.abc import Iterable

from srd_arena.content.spells.metadata import (
    SpellCastingTimeSchema,
    SpellComponentsSchema,
    SpellDurationSchema,
    SpellMaterialComponentSchema,
    SpellRangeSchema,
)
from srd_arena.domain.spells.metadata import (
    SpellCastingTime,
    SpellComponents,
    SpellDuration,
    SpellMaterialComponent,
    SpellRange,
    SpellRangeDistance,
)


def build_casting_times(
    values: Iterable[SpellCastingTimeSchema],
) -> tuple[SpellCastingTime, ...]:
    """Translate every authored casting-time alternative.

    >>> from srd_arena.content.spells.metadata import SpellCastingTimeSchema
    >>> build_casting_times([SpellCastingTimeSchema(number=1, unit="action")])
    (SpellCastingTime(number=1, unit='action', trigger=None, label=None),)
    """
    return tuple(
        SpellCastingTime(value.number, value.unit, value.condition, value.note)
        for value in values
    )


def build_spell_range(value: SpellRangeSchema | None) -> SpellRange | None:
    """Translate a spell's authored shape and distance.

    >>> from srd_arena.content.spells.metadata import SpellRangeSchema
    >>> build_spell_range(SpellRangeSchema.model_validate({
    ...     "type": "point", "distance": {"type": "feet", "amount": 60}
    ... }))
    SpellRange(kind='point', distance=SpellRangeDistance(kind='feet', amount=60))
    >>> build_spell_range(None) is None
    True
    """
    if value is None:
        return None
    return SpellRange(
        value.type,
        SpellRangeDistance(value.distance.type, value.distance.amount),
    )


def build_spell_durations(
    values: Iterable[SpellDurationSchema],
) -> tuple[SpellDuration, ...]:
    """Translate intrinsic duration variants without retaining source mappings.

    >>> from srd_arena.content.spells.metadata import SpellDurationSchema
    >>> build_spell_durations([SpellDurationSchema.model_validate({
    ...     "type": "timed", "concentration": True,
    ...     "duration": {"type": "minute", "amount": 1},
    ... })])
    (SpellDuration(kind='timed', amount=1, unit='minute', concentration=True, ending_events=()),)
    """
    return tuple(_build_spell_duration(value) for value in values)


def build_spell_components(value: SpellComponentsSchema) -> SpellComponents:
    """Translate component presence and retain typed material details.

    >>> source = SpellComponentsSchema.model_validate({
    ...     "v": True, "m": {"text": "diamond dust", "cost": 10000,
    ...     "consume": True},
    ... })
    >>> sorted(build_spell_components(source).required)
    ['material', 'verbal']
    """
    return SpellComponents(
        verbal=value.v,
        somatic=value.s,
        material=_build_material_component(value.m),
    )


def _build_spell_duration(value: SpellDurationSchema) -> SpellDuration:
    timing = value.duration
    return SpellDuration(
        value.type,
        amount=timing.amount if timing is not None else None,
        unit=timing.type if timing is not None else None,
        concentration=value.concentration,
        ending_events=tuple(value.ends),
    )


def _build_material_component(
    value: str | SpellMaterialComponentSchema | None,
) -> SpellMaterialComponent | None:
    if value is None:
        return None
    if isinstance(value, str):
        return SpellMaterialComponent(value)
    return SpellMaterialComponent(value.text, value.cost, value.consume)
