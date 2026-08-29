"""Extract normalized rule metadata from validated spell content."""

import re

from srd_arena.content.capabilities import DamageEffectSchema
from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    RemoveEffectSchema,
    RepeatResolutionSchema,
    SavingThrowResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.schema import SpellSchema


def spell_damage_dice(raw: SpellSchema) -> str | None:
    """Return the base damage expression authored for a spell outcome.

    >>> spell = SpellSchema.model_construct(
    ...     capability=None, entries=["Damage: {@damage 8d6}."], range={})
    >>> spell_damage_dice(spell)
    '8d6'
    """

    if raw.capability is not None:
        resolution = raw.capability.resolution.root
        if isinstance(resolution, RepeatResolutionSchema):
            resolution = resolution.resolution.root
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
            if isinstance(resolution, AutomaticResolutionSchema)
            else None
        )
        if outcome is not None:
            damage = next(
                (
                    effect.root
                    for effect in outcome.effects
                    if isinstance(effect.root, DamageEffectSchema)
                ),
                None,
            )
            if damage is not None:
                return damage.dice
    for entry in raw.entries:
        if not isinstance(entry, str):
            continue
        match = re.search(r"\{@damage ([^}]+)\}", entry)
        if match is not None:
            return match.group(1)
    return None


def spell_removable_conditions(raw: SpellSchema) -> tuple[str, ...]:
    """Collect condition kinds that the spell can explicitly remove.

    >>> spell = SpellSchema.model_construct(
    ...     capability=None,
    ...     entries=["End one condition on it: {@condition Blinded}."],
    ...     range={})
    >>> spell_removable_conditions(spell)
    ('blinded',)
    """

    if raw.capability is not None:
        resolution = raw.capability.resolution.root
        if isinstance(resolution, RepeatResolutionSchema):
            resolution = resolution.resolution.root
        if isinstance(resolution, AutomaticResolutionSchema):
            conditions = tuple(
                condition
                for effect in resolution.outcome.effects
                if isinstance(effect.root, RemoveEffectSchema)
                and "condition" in effect.root.removable
                for condition in effect.root.conditions
            )
            if conditions:
                return conditions
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return ()
    text = " ".join(text_parts)
    if "end one condition on it:" not in text.casefold():
        return ()
    return tuple(
        match.casefold() for match in re.findall(r"\{@condition ([^|}]+)", text)
    )


def remove_effect_selection(raw: SpellSchema) -> str | None:
    """Return the spell's authored choice among removable effect categories.

    >>> spell = SpellSchema.model_validate({
    ...     "name": "Restore", "source": "TEST", "level": 2, "school": "A",
    ...     "implementation": {"status": "complete"},
    ...     "capability": {
    ...         "target": {"type": "creature"},
    ...         "resolution": {"type": "automatic", "outcome": {"effects": [{
    ...             "type": "remove_effect", "selection": "one",
    ...             "removable": ["condition", "curse"]
    ...         }]}},
    ...     },
    ... })
    >>> remove_effect_selection(spell)
    'one'
    """

    if raw.capability is None:
        return None
    resolution = raw.capability.resolution.root
    if isinstance(resolution, RepeatResolutionSchema):
        resolution = resolution.resolution.root
    if not isinstance(resolution, AutomaticResolutionSchema):
        return None
    removal = next(
        (
            effect.root
            for effect in resolution.outcome.effects
            if isinstance(effect.root, RemoveEffectSchema)
        ),
        None,
    )
    return removal.selection if removal is not None else None


def spell_removable_effect_kinds(raw: SpellSchema) -> tuple[str, ...]:
    """Collect the authored effect categories that a spell can remove.

    >>> spell = SpellSchema.model_validate({
    ...     "name": "Restore", "source": "TEST", "level": 2, "school": "A",
    ...     "implementation": {"status": "complete"},
    ...     "capability": {
    ...         "target": {"type": "creature"},
    ...         "resolution": {"type": "automatic", "outcome": {"effects": [{
    ...             "type": "remove_effect", "selection": "one",
    ...             "removable": ["condition", "curse"]
    ...         }]}},
    ...     },
    ... })
    >>> spell_removable_effect_kinds(spell)
    ('condition', 'curse')
    """

    if raw.capability is None:
        return ()
    resolution = raw.capability.resolution.root
    if isinstance(resolution, RepeatResolutionSchema):
        resolution = resolution.resolution.root
    if not isinstance(resolution, AutomaticResolutionSchema):
        return ()
    removal = next(
        (
            effect.root
            for effect in resolution.outcome.effects
            if isinstance(effect.root, RemoveEffectSchema)
        ),
        None,
    )
    return tuple(removal.removable) if removal is not None else ()


def spell_geometry_mode(raw: SpellSchema) -> str:
    """Map authored area metadata to the domain's grid geometry mode.

    >>> cone = SpellSchema.model_validate({
    ...     "name": "Cone", "source": "TEST", "level": 1, "school": "V",
    ...     "range": {"type": "cone", "distance": {"type": "feet", "amount": 15}},
    ... })
    >>> spell_geometry_mode(cone)
    'directional_area'
    """

    if raw.capability is not None and raw.capability.target.type == "area":
        return (
            "directional_area"
            if raw.capability.target.origin == "self"
            else "point_area"
        )
    range_type = raw.range.type if raw.range is not None else None
    if spell_removable_conditions(raw):
        return "point_target"
    if range_type in {"cone", "line", "cube"}:
        return "directional_area"
    if range_type in {"radius", "sphere", "cylinder", "emanation"}:
        return "non_directional_area"
    if range_type == "point" and spell_area_size_feet(raw) is not None:
        return "point_area"
    return "point_target"


def spell_area_size_feet(raw: SpellSchema) -> int | None:
    """Return the authored linear size used to construct the spell's area.

    >>> spell = SpellSchema.model_validate({
    ...     "name": "Sphere", "source": "TEST", "level": 1, "school": "V",
    ...     "entries": ["A 20-foot-radius sphere."],
    ...     "range": {"type": "point", "distance": {"type": "feet", "amount": 60}},
    ... })
    >>> spell_area_size_feet(spell)
    20
    """

    if raw.capability is not None and raw.capability.target.type == "area":
        geometry = raw.capability.target.geometry
        return geometry.radius_feet or geometry.length_feet
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
