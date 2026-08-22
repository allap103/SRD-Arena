import re

from .schema import SpellSchema
from srd_arena.content.capabilities import (
    DamageEffectSchema,
)
from .resolution import (
    AutomaticResolutionSchema,
    RepeatResolutionSchema,
    RemoveEffectSchema,
    SavingThrowResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.translation.scaling import slot_damage_increment
from srd_arena.content.spells.translation.targeting import normalize_save_ability
from srd_arena.domain.spells import (
    FollowUpSpellResolution,
    SpellDamage,
)


def _follow_up_resolution(
    raw: SpellSchema,
    step: object,
) -> FollowUpSpellResolution:
    target = getattr(step, "target", None)
    resolution_wrapper = getattr(step, "resolution", None)
    resolution = getattr(resolution_wrapper, "root", None)
    if target is None or target.type != "area" or target.origin != "target":
        raise ValueError("Follow-up spell resolutions require a target-origin area.")
    if not isinstance(resolution, SavingThrowResolutionSchema):
        raise ValueError("Only saving-throw follow-up resolutions are executable.")
    damage = tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in resolution.failure.effects
        if isinstance(effect.root, DamageEffectSchema)
    )
    return FollowUpSpellResolution(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            normalize_save_ability(resolution.ability)
            if resolution.ability is not None
            else None
        ),
        half_damage_on_save=resolution.success_damage == "half",
        area_radius_feet=target.geometry.radius_feet,
        slot_damage_increment=slot_damage_increment(
            raw,
            damage_types={entry.damage_type for entry in damage},
        ),
    )


def _spell_damage_dice(raw: SpellSchema) -> str | None:
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


def _spell_removable_conditions(raw: SpellSchema) -> tuple[str, ...]:
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


def _remove_effect_selection(raw: SpellSchema) -> str | None:
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


def _spell_removable_effect_kinds(raw: SpellSchema) -> tuple[str, ...]:
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


def _spell_geometry_mode(raw: SpellSchema) -> str:
    if raw.capability is not None and raw.capability.target.type == "area":
        return (
            "directional_area"
            if raw.capability.target.origin == "self"
            else "point_area"
        )
    range_type = (
        raw.range.get("type") if isinstance(raw.range.get("type"), str) else None
    )
    if _spell_removable_conditions(raw):
        return "point_target"
    if range_type in {"cone", "line", "cube"}:
        return "directional_area"
    if range_type in {"radius", "sphere", "cylinder", "emanation"}:
        return "non_directional_area"
    if range_type == "point" and _spell_area_size_feet(raw) is not None:
        return "point_area"
    return "point_target"


def _spell_area_size_feet(raw: SpellSchema) -> int | None:
    if raw.capability is not None and raw.capability.target.type == "area":
        geometry = raw.capability.target.geometry
        return geometry.radius_feet or geometry.length_feet
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
