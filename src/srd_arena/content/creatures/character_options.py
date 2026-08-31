"""Apply the supported authored class choices while building a creature."""

import re

from srd_arena.content.character_options.classes import (
    ClassCatalog,
    ClassRecord,
    OptionalFeatureCatalog,
    normalize_optional_feature_effects,
)
from srd_arena.content.character_options.classes.optional_feature_schema import (
    OptionalFeatureSchema,
)
from srd_arena.content.character_options.classes.schema import (
    ClassFeatureReferenceSchema,
    ClassFeatureSchema,
    ClassSchema,
)
from srd_arena.domain.creatures import ClassFeature
from srd_arena.domain.effects.triggered import TriggeredEffect

from .schema import CreatureSchema


def resolve_optional_feature_effects(
    schema: CreatureSchema,
    catalog: OptionalFeatureCatalog | None,
) -> list[TriggeredEffect]:
    """Collect the optional-feature changes selected by a creature build.

    >>> schema = CreatureSchema(
    ...     id="fighter", optional_features=[{
    ...         "name": "Great Weapon Fighting", "source": "PHB"}])
    >>> resolve_optional_feature_effects(schema, None)[0].id
    Traceback (most recent call last):
    ...
    ValueError: Creature references optional feature 'Great Weapon Fighting', but no optional feature catalog was loaded.
    """

    effects: list[TriggeredEffect] = []
    for reference in schema.optional_features:
        if catalog is None:
            raise ValueError(
                f"Creature references optional feature '{reference.name}', "
                "but no optional feature catalog was loaded."
            )
        try:
            feature = catalog.find(reference.name, reference.source)
        except KeyError:
            normalized = normalize_optional_feature_effects(
                OptionalFeatureSchema(
                    name=reference.name,
                    source=reference.source or "",
                )
            )
            if not normalized:
                raise
            effects.extend(normalized)
        else:
            effects.extend(normalize_optional_feature_effects(feature))
    return effects


def find_class_record(
    schema: CreatureSchema,
    classes: ClassCatalog | None,
) -> ClassRecord | None:
    """Resolve the class record referenced by a creature's character levels.

    >>> from srd_arena.content.common.catalog import SourceCatalog
    >>> definition = ClassSchema(name="Fighter", source="X")
    >>> record = ClassRecord(definition, ())
    >>> catalog = SourceCatalog(
    ...     [record], name_of=lambda item: item.definition.public_name,
    ...     source_of=lambda item: item.definition.source)
    >>> schema = CreatureSchema(id="hero", class_ref={"name": "Fighter"})
    >>> find_class_record(schema, catalog) is record
    True
    """

    if schema.class_ref is None:
        return None
    if classes is None:
        raise ValueError(
            f"Creature references class '{schema.class_ref.name}', "
            "but no class catalog was loaded."
        )
    return classes.find(schema.class_ref.name, schema.class_ref.source)


def resolve_class_features(
    class_record: ClassRecord | None,
    level: int,
) -> list[ClassFeature]:
    """Collect supported class features earned at or below a level.

    >>> definition = ClassSchema(
    ...     name="Fighter", source="X",
    ...     classFeatures=["Extra Attack|Fighter|X|5"])
    >>> features = resolve_class_features(ClassRecord(definition, ()), 5)
    >>> (features[0].id, features[0].data["attacks"])
    ('extra_attack', 2)
    """

    if class_record is None:
        return []
    resolved: list[ClassFeature] = []
    for feature_ref in class_record.definition.class_features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None or parsed[1] > level:
            continue
        feature = _normalize_class_feature(
            class_record.definition.public_name,
            parsed[0],
            parsed[1],
            class_record,
            level,
        )
        if feature is not None:
            resolved.append(feature)
    return resolved


def _parse_class_feature_reference(
    feature_ref: str | ClassFeatureReferenceSchema,
) -> tuple[str, int] | None:
    raw_ref = feature_ref if isinstance(feature_ref, str) else feature_ref.class_feature
    parts = raw_ref.split("|")
    for part in reversed(parts):
        if part.isdigit():
            return parts[0], int(part)
    return None


def _normalize_class_feature(
    class_name: str,
    feature_name: str,
    feature_level: int,
    class_record: ClassRecord | None = None,
    creature_level: int = 1,
) -> ClassFeature | None:
    attacks = {
        "Extra Attack": 2,
        "Extra Attack (2)": 3,
        "Extra Attack (3)": 4,
        "Two Extra Attacks": 3,
        "Three Extra Attacks": 4,
    }.get(feature_name)
    if attacks is not None:
        return ClassFeature(
            id="extra_attack",
            name=feature_name,
            source_class=class_name,
            level=feature_level,
            data={"attacks": attacks},
        )
    if feature_name == "Second Wind":
        return ClassFeature(
            id="second_wind",
            name=feature_name,
            source_class=class_name,
            level=feature_level,
            data={
                "uses": _second_wind_uses(class_record, creature_level),
                **_second_wind_healing_dice(
                    class_record,
                    feature_name,
                    feature_level,
                ),
            },
        )
    if feature_name == "Action Surge":
        return ClassFeature(
            id="action_surge",
            name=feature_name,
            source_class=class_name,
            level=feature_level,
            data={"uses": _action_surge_uses(class_record, creature_level)},
        )
    return None


def _second_wind_uses(
    class_record: ClassRecord | None,
    feature_level: int,
) -> int:
    if class_record is None or class_record.definition.source != "XPHB":
        return 1
    table_value = _class_table_value(
        class_record.definition,
        "Second Wind",
        feature_level,
    )
    if table_value is None:
        return 2
    try:
        return int(table_value)
    except ValueError:
        return 2


def _action_surge_uses(
    class_record: ClassRecord | None,
    feature_level: int,
) -> int:
    if class_record is None:
        return 1
    table_value = _class_table_value(
        class_record.definition,
        "Action Surge",
        feature_level,
    )
    if table_value is None:
        return 1
    try:
        return int(table_value)
    except ValueError:
        return 1


def _second_wind_healing_dice(
    class_record: ClassRecord | None,
    feature_name: str,
    feature_level: int,
) -> dict[str, int]:
    feature_entry = _class_feature_entry(
        class_record,
        feature_name,
        feature_level,
    )
    dice = _first_dice_expression(
        feature_entry.entries if feature_entry is not None else None
    )
    dice_count, dice_sides = dice or (1, 10)
    return {
        "healing_die_count": dice_count,
        "healing_die_sides": dice_sides,
    }


def _class_feature_entry(
    class_record: ClassRecord | None,
    feature_name: str,
    feature_level: int,
) -> ClassFeatureSchema | None:
    if class_record is None:
        return None
    definition = class_record.definition
    return next(
        (
            entry
            for entry in class_record.features
            if entry.public_name == feature_name
            and entry.level == feature_level
            and entry.class_name == definition.name
            and entry.class_source == definition.source
        ),
        None,
    )


def _first_dice_expression(value: object) -> tuple[int, int] | None:
    if isinstance(value, str):
        match = re.search(r"\{@dice\s+(\d+)d(\d+)", value)
        return (int(match.group(1)), int(match.group(2))) if match is not None else None
    if isinstance(value, dict):
        values = tuple(value.values())
    elif isinstance(value, list):
        values = tuple(value)
    else:
        return None
    return next(
        (
            dice
            for nested_value in values
            if (dice := _first_dice_expression(nested_value)) is not None
        ),
        None,
    )


def _class_table_value(
    definition: ClassSchema,
    column_label: str,
    level: int,
) -> str | None:
    for group in definition.table_groups:
        try:
            column_index = group.column_labels.index(column_label)
        except ValueError:
            continue
        row_index = level - 1
        if row_index < 0 or row_index >= len(group.rows):
            continue
        row = group.rows[row_index]
        if isinstance(row, list) and column_index < len(row):
            return str(row[column_index])
    return None
