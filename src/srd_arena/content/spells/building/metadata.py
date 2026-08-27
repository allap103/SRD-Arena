"""Provide metadata support for the building package."""

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
    """Handle spell damage dice."""

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
    """Handle spell removable conditions."""

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
    """Remove effect selection."""

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
    """Handle spell removable effect kinds."""

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
    """Handle spell geometry mode."""

    if raw.capability is not None and raw.capability.target.type == "area":
        return (
            "directional_area"
            if raw.capability.target.origin == "self"
            else "point_area"
        )
    range_type = (
        raw.range.get("type") if isinstance(raw.range.get("type"), str) else None
    )
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
    """Handle spell area size feet."""

    if raw.capability is not None and raw.capability.target.type == "area":
        geometry = raw.capability.target.geometry
        return geometry.radius_feet or geometry.length_feet
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
