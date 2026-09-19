"""Translate authored visible equipment into domain appearance descriptions."""

from srd_arena.domain.creatures import (
    ApparentArmorCategory,
    ApparentFocusKind,
    ObservableAppearance,
)

from .schema import (
    CreatureItemReferenceSchema,
    CreatureSchema,
    ItemIdOrReference,
    ObservableAppearanceSchema,
)
from .stat_block_schema import BestiaryGearSchema, BestiaryMonsterSchema

_ARMOR_CATEGORIES: tuple[tuple[str, ApparentArmorCategory], ...] = (
    ("studded leather", ApparentArmorCategory.LIGHT),
    ("leather", ApparentArmorCategory.LIGHT),
    ("hide armor", ApparentArmorCategory.MEDIUM),
    ("chain shirt", ApparentArmorCategory.MEDIUM),
    ("scale mail", ApparentArmorCategory.MEDIUM),
    ("breastplate", ApparentArmorCategory.MEDIUM),
    ("half plate", ApparentArmorCategory.MEDIUM),
    ("ring mail", ApparentArmorCategory.HEAVY),
    ("chain mail", ApparentArmorCategory.HEAVY),
    ("splint", ApparentArmorCategory.HEAVY),
    ("plate", ApparentArmorCategory.HEAVY),
)


def build_observable_appearance(
    creature: CreatureSchema,
    stat_block: BestiaryMonsterSchema | None,
) -> ObservableAppearance:
    """Build the public visual description for one creature template.

    Explicit creature content wins over stat-block content. The fallback reads
    only ordinary held/worn equipment; it never derives appearance from Armor
    Class or another private statistic.
    """

    gear = (
        tuple(_gear_name(entry) for entry in stat_block.gear)
        if stat_block is not None
        else ()
    )
    armor_name = _optional_reference_name(creature.equipment.get("armor"))
    held = tuple(
        name
        for reference in (
            creature.equipment.get("right_hand"),
            creature.equipment.get("left_hand"),
        )
        if (name := _optional_reference_name(reference)) is not None
    )
    inferred = _infer_ordinary_appearance(
        (*gear, *held),
        explicit_armor=armor_name,
        apparent_creature_type=None,
    )
    authored = creature.appearance or (
        stat_block.appearance if stat_block is not None else None
    )
    return (
        _overlay_authored_appearance(inferred, authored)
        if authored is not None
        else inferred
    )


def _overlay_authored_appearance(
    inferred: ObservableAppearance,
    authored: ObservableAppearanceSchema,
) -> ObservableAppearance:
    fields = authored.model_fields_set
    return ObservableAppearance(
        armor_label=(
            authored.armor_label if "armor_label" in fields else inferred.armor_label
        ),
        armor_category=(
            ApparentArmorCategory(authored.armor_category)
            if "armor_category" in fields
            else inferred.armor_category
        ),
        has_shield=(
            authored.has_shield if "has_shield" in fields else inferred.has_shield
        ),
        visible_weapons=(
            authored.visible_weapons
            if "visible_weapons" in fields
            else inferred.visible_weapons
        ),
        spellcasting_focus_label=(
            authored.spellcasting_focus_label
            if "spellcasting_focus_label" in fields
            else inferred.spellcasting_focus_label
        ),
        spellcasting_focus_kind=(
            ApparentFocusKind(authored.spellcasting_focus_kind)
            if "spellcasting_focus_kind" in fields
            else inferred.spellcasting_focus_kind
        ),
        obvious_features=(
            authored.obvious_features
            if "obvious_features" in fields
            else inferred.obvious_features
        ),
        apparent_creature_type=(
            authored.apparent_creature_type
            if "apparent_creature_type" in fields
            else inferred.apparent_creature_type
        ),
    )


def _infer_ordinary_appearance(
    item_names: tuple[str, ...],
    *,
    explicit_armor: str | None,
    apparent_creature_type: str | None,
) -> ObservableAppearance:
    armor_label = explicit_armor
    has_shield = False
    weapons: list[str] = []
    focus_label: str | None = None
    focus_kind = ApparentFocusKind.NONE

    for name in item_names:
        normalized = name.casefold()
        if normalized == "shield":
            has_shield = True
        elif _armor_category(name) is not ApparentArmorCategory.UNKNOWN:
            armor_label = armor_label or name
        elif "component pouch" in normalized:
            focus_label = name
            focus_kind = ApparentFocusKind.COMPONENT_POUCH
        elif any(word in normalized for word in ("focus", "orb", "wand", "staff")):
            focus_label = name
            focus_kind = ApparentFocusKind.UNKNOWN
        else:
            weapons.append(name)

    return ObservableAppearance(
        armor_label=armor_label,
        armor_category=_armor_category(armor_label),
        has_shield=has_shield,
        visible_weapons=tuple(dict.fromkeys(weapons)),
        spellcasting_focus_label=focus_label,
        spellcasting_focus_kind=focus_kind,
        apparent_creature_type=apparent_creature_type,
    )


def _armor_category(name: str | None) -> ApparentArmorCategory:
    if name is None:
        return ApparentArmorCategory.UNKNOWN
    normalized = name.casefold()
    return next(
        (category for marker, category in _ARMOR_CATEGORIES if marker in normalized),
        ApparentArmorCategory.UNKNOWN,
    )


def _optional_reference_name(reference: ItemIdOrReference | None) -> str | None:
    return _reference_name(reference) if reference is not None else None


def _reference_name(reference: ItemIdOrReference) -> str:
    if isinstance(reference, CreatureItemReferenceSchema):
        return reference.name
    return reference.split("|", 1)[0].replace("_", " ").strip().title()


def _gear_name(reference: str | BestiaryGearSchema) -> str:
    return _reference_name(
        reference.item if isinstance(reference, BestiaryGearSchema) else reference
    )
