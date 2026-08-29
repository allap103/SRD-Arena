"""Translate authored creature attributes into domain values."""

from srd_arena.content.character_options.classes import ClassRecord
from srd_arena.domain.creatures import Attributes, Movement, normalize_size

from .schema import CreatureSchema
from .stat_block_schema import BestiaryMonsterSchema
from .statistics import challenge_rating_proficiency_bonus


def build_creature_attributes(
    schema: CreatureSchema,
    stat_block: BestiaryMonsterSchema | None,
    class_record: ClassRecord | None,
) -> Attributes:
    """Translate authored ability scores, proficiencies, and movement into domain attributes.

    A creature without a referenced stat block uses its directly authored values.

    >>> schema = CreatureSchema(
    ...     id="scout",
    ...     attributes={"dexterity": 14, "movement": {"speed_feet": 25}},
    ... )
    >>> attributes = build_creature_attributes(schema, None, None)
    >>> (attributes.dexterity, attributes.movement.speed_feet)
    (14, 25)
    """

    if stat_block is None:
        attributes = schema.attributes.model_dump(exclude={"movement"})
        proficiencies = _merge_proficiencies(
            schema.attributes.proficiencies, _class_proficiencies(class_record)
        )
        attributes["proficiencies"] = proficiencies
        attributes["saving_throw_proficiencies"] = _saving_throw_proficiencies(
            proficiencies
        )
        return Attributes(
            **attributes,
            movement=Movement(**schema.attributes.movement.model_dump()),
        )

    proficiencies = _merge_proficiencies(
        schema.attributes.proficiencies,
        _class_proficiencies(class_record),
        {"saving_throws": [ability.casefold() for ability in stat_block.save]},
    )
    return Attributes(
        base_health=(
            stat_block.average_hit_points
            if stat_block.average_hit_points is not None
            else schema.attributes.base_health
        ),
        level=schema.attributes.level,
        movement=Movement(
            speed_feet=(
                stat_block.walk_speed
                if stat_block.walk_speed is not None
                else schema.attributes.movement.speed_feet
            ),
            burrow_feet=_movement_speed(stat_block, "burrow"),
            climb_feet=_movement_speed(stat_block, "climb"),
            fly_feet=_movement_speed(stat_block, "fly"),
            swim_feet=_movement_speed(stat_block, "swim"),
        ),
        strength=stat_block.strength,
        dexterity=stat_block.dexterity,
        constitution=stat_block.constitution,
        wisdom=stat_block.wisdom,
        intelligence=stat_block.intelligence,
        charisma=stat_block.charisma,
        base_armor_class=_stat_block_base_ac(
            stat_block, schema.attributes.base_armor_class
        ),
        proficiency_bonus=challenge_rating_proficiency_bonus(
            stat_block.challenge_rating
        ),
        proficiencies=proficiencies,
        saving_throw_proficiencies=_saving_throw_proficiencies(proficiencies),
    )


def build_creature_size(
    schema: CreatureSchema,
    stat_block: BestiaryMonsterSchema | None,
) -> str:
    """Normalize an authored size label to the supported domain size category.

    >>> schema = CreatureSchema(id="ogre", metadata={"size": "large"})
    >>> build_creature_size(schema, None)
    'L'
    """

    if stat_block is not None:
        return normalize_size(stat_block.primary_size)
    return _normalize_size_value(schema.metadata.get("size"))


def _normalize_size_value(value: object) -> str:
    if isinstance(value, list) and value:
        return normalize_size(value[0])
    return normalize_size(value)


def _merge_proficiencies(*sources: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for source in sources:
        for key, value in source.items():
            if isinstance(value, list):
                existing = merged.setdefault(key, [])
                if isinstance(existing, list):
                    existing.extend(item for item in value if item not in existing)
            else:
                merged[key] = value
    return merged


def _class_proficiencies(class_record: ClassRecord | None) -> dict[str, object]:
    if class_record is None:
        return {}
    definition = class_record.definition
    proficiencies: dict[str, object] = {}
    proficiencies["weapons"] = list(definition.starting_proficiencies.weapons)
    ability_names = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    proficiencies["saving_throws"] = [
        ability_names.get(value.casefold(), value.casefold())
        for value in definition.proficiency
    ]
    return proficiencies


def _saving_throw_proficiencies(
    proficiencies: dict[str, object],
) -> frozenset[str]:
    authored = proficiencies.get("saving_throws", ())
    if not isinstance(authored, list):
        return frozenset()
    aliases = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    return frozenset(
        aliases.get(value.casefold(), value.casefold())
        for value in authored
        if isinstance(value, str)
    )


def _stat_block_base_ac(stat_block: BestiaryMonsterSchema, default: int) -> int:
    armor_class = _stat_block_ac(stat_block, default)
    dexterity = stat_block.dexterity
    return armor_class - ((dexterity - 10) // 2)


def _stat_block_ac(stat_block: BestiaryMonsterSchema, default: int) -> int:
    return stat_block.armor_class if stat_block.armor_class is not None else default


def _movement_speed(
    stat_block: BestiaryMonsterSchema,
    mode: str,
) -> int | None:
    return stat_block.speed.feet_for(mode)
