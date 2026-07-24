from srd_arena.content.catalogs import ClassRecord
from srd_arena.content.schemas import CreatureSchema
from srd_arena.content.schemas.bestiary import BestiaryMonsterSchema
from srd_arena.domain.creatures import Attributes, Movement, normalize_size
from .creature_statistics import challenge_rating_proficiency_bonus


def build_creature_attributes(
    schema: CreatureSchema,
    stat_block: BestiaryMonsterSchema | None,
    class_record: ClassRecord | None,
) -> Attributes:
    if stat_block is None:
        attributes = schema.attributes.model_dump(exclude={"movement"})
        attributes["proficiencies"] = _merge_proficiencies(
            schema.attributes.proficiencies, _class_proficiencies(class_record)
        )
        return Attributes(
            **attributes,
            movement=Movement(**schema.attributes.movement.model_dump()),
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
            feet_per_square=schema.attributes.movement.feet_per_square,
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
        base_armor_class=_stat_block_base_ac(stat_block, schema.attributes.base_armor_class),
        proficiency_bonus=challenge_rating_proficiency_bonus(
            stat_block.challenge_rating
        ),
        proficiencies=_merge_proficiencies(
            schema.attributes.proficiencies,
            _class_proficiencies(class_record),
            {
                "saving_throws": [
                    ability.casefold()
                    for ability in stat_block.save
                ]
            },
        ),
    )


def build_creature_size(
    schema: CreatureSchema,
    stat_block: BestiaryMonsterSchema | None,
) -> str:
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
        "str": "strength", "dex": "dexterity", "con": "constitution",
        "int": "intelligence", "wis": "wisdom", "cha": "charisma",
    }
    proficiencies["saving_throws"] = [
        ability_names.get(value.casefold(), value.casefold())
        for value in definition.proficiency
    ]
    return proficiencies


def _stat_block_base_ac(stat_block: BestiaryMonsterSchema, default: int) -> int:
    armor_class = _stat_block_ac(stat_block, default)
    dexterity = stat_block.dexterity
    return armor_class - ((dexterity - 10) // 2)


def _stat_block_ac(stat_block: BestiaryMonsterSchema, default: int) -> int:
    return (
        stat_block.armor_class
        if stat_block.armor_class is not None
        else default
    )


def _movement_speed(
    stat_block: BestiaryMonsterSchema,
    mode: str,
) -> int | None:
    value = stat_block.speed.get(mode)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, dict):
        number = value.get("number")
        if isinstance(number, int) and not isinstance(number, bool):
            return number
    return None
