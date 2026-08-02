import re

from srd_arena.content.catalogs import SpellCatalog
from srd_arena.content.schemas.spells import SpellSchema
from srd_arena.content.sources import slug
from srd_arena.domain.spells import Spell
from srd_arena.domain.creatures import CreatureTypeRequirement


def build_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    raw = _find_spell(name, source, catalog)
    return Spell(
        id=slug(raw.public_name),
        name=raw.public_name,
        source=raw.source,
        level=raw.level,
        school=raw.school,
        casting_time=tuple(raw.time),
        range_data=dict(raw.range),
        duration_data=tuple(raw.duration),
        components=dict(raw.components),
        saving_throw_abilities=tuple(
            _normalize_save_ability(value)
            for value in raw.saving_throw
        ),
        condition_inflict=tuple(raw.condition_inflict),
        removable_conditions=_spell_removable_conditions(raw),
        damage_dice=_spell_damage_dice(raw),
        damage_inflict=tuple(raw.damage_inflict),
        area_tags=tuple(raw.area_tags),
        geometry_mode=_spell_geometry_mode(raw),
        area_size_feet=_spell_area_size_feet(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        target_requirements=(
            (CreatureTypeRequirement(tuple(raw.affects_creature_type)),)
            if raw.affects_creature_type
            else ()
        ),
    )


def _find_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> SpellSchema:
    if catalog is None:
        raise ValueError(
            f"Creature references spell '{name}', but no spell catalog was loaded."
        )
    return catalog.find(name, source)


def _normalize_save_ability(value: str) -> str:
    aliases = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    normalized = value.casefold()
    return aliases.get(normalized, normalized)


def _spell_damage_dice(raw: SpellSchema) -> str | None:
    for entry in raw.entries:
        if not isinstance(entry, str):
            continue
        match = re.search(r"\{@damage ([^}]+)\}", entry)
        if match is not None:
            return match.group(1)
    return None


def _spell_removable_conditions(raw: SpellSchema) -> tuple[str, ...]:
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return ()
    text = " ".join(text_parts)
    if "end one condition on it:" not in text.casefold():
        return ()
    return tuple(
        match.casefold()
        for match in re.findall(r"\{@condition ([^|}]+)", text)
    )


def _spell_geometry_mode(raw: SpellSchema) -> str:
    range_type = (
        raw.range.get("type")
        if isinstance(raw.range.get("type"), str)
        else None
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
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
