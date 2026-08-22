"""Small normalization helpers shared by capability builders."""

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas.durations import EffectDurationSchema


def build_duration(
    value: EffectDurationSchema | None,
) -> domain.EffectDuration | None:
    if value is None:
        return None
    return domain.EffectDuration(
        kind=value.type,
        amount=getattr(value, "amount", None),
        unit=getattr(value, "unit", None),
        creature=getattr(value, "creature", None),
        turn_offset=getattr(value, "turn_offset", 0),
        events=tuple(getattr(value, "events", ())),
    )


def normalize_ability(value: str | None) -> str | None:
    if value is None:
        return None
    return {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }.get(value, value)


def resolution_root(value: object) -> object:
    return getattr(value, "root", value)
