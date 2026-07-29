from ..schemas import CreatureSchema
from ...domain.creatures import Attributes, Movement
from ...domain.creatures import normalize_size


def build_creature_attributes(
    schema: CreatureSchema,
    stat_block: dict | None,
    class_block: dict | None,
) -> Attributes:
    if stat_block is None:
        attributes = schema.attributes.model_dump(exclude={"movement"})
        attributes["proficiencies"] = _merge_proficiencies(
            schema.attributes.proficiencies, _class_proficiencies(class_block)
        )
        return Attributes(
            **attributes,
            movement=Movement(**schema.attributes.movement.model_dump()),
        )

    return Attributes(
        base_health=int(
            stat_block.get("hp", {}).get("average", schema.attributes.base_health)
        ),
        level=schema.attributes.level,
        movement=Movement(
            speed_feet=int(
                stat_block.get("speed", {}).get(
                    "walk", schema.attributes.movement.speed_feet
                )
            ),
            feet_per_square=schema.attributes.movement.feet_per_square,
        ),
        strength=int(stat_block.get("str", schema.attributes.strength)),
        dexterity=int(stat_block.get("dex", schema.attributes.dexterity)),
        constitution=int(stat_block.get("con", schema.attributes.constitution)),
        wisdom=int(stat_block.get("wis", schema.attributes.wisdom)),
        intelligence=int(stat_block.get("int", schema.attributes.intelligence)),
        charisma=int(stat_block.get("cha", schema.attributes.charisma)),
        base_armor_class=_stat_block_base_ac(
            stat_block, schema.attributes.base_armor_class
        ),
        proficiencies=_merge_proficiencies(
            schema.attributes.proficiencies, _class_proficiencies(class_block)
        ),
    )


def build_creature_size(schema: CreatureSchema, stat_block: dict | None) -> str:
    if stat_block is not None:
        size = _normalize_size_value(stat_block.get("size"))
        if size != "M" or stat_block.get("size") is not None:
            return size
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


def _class_proficiencies(class_block: dict | None) -> dict[str, object]:
    if class_block is None:
        return {}
    starting = class_block.get("startingProficiencies", {})
    weapons = starting.get("weapons", []) if isinstance(starting, dict) else []
    proficiencies: dict[str, object] = {}
    if isinstance(weapons, list):
        proficiencies["weapons"] = list(weapons)
    saving_throws = class_block.get("proficiency", [])
    if isinstance(saving_throws, list):
        ability_names = {
            "str": "strength",
            "dex": "dexterity",
            "con": "constitution",
            "int": "intelligence",
            "wis": "wisdom",
            "cha": "charisma",
        }
        proficiencies["saving_throws"] = [
            ability_names.get(str(value).casefold(), str(value).casefold())
            for value in saving_throws
        ]
    return proficiencies


def _stat_block_base_ac(stat_block: dict, default: int) -> int:
    armor_class = _stat_block_ac(stat_block, default)
    dexterity = int(stat_block.get("dex", 10))
    return armor_class - ((dexterity - 10) // 2)


def _stat_block_ac(stat_block: dict, default: int) -> int:
    ac = stat_block.get("ac")
    if not isinstance(ac, list) or not ac:
        return default
    first = ac[0]
    if isinstance(first, int):
        return first
    if isinstance(first, dict) and isinstance(first.get("ac"), int):
        return first["ac"]
    return default
