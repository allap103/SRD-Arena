"""Describe the ordinary visual information a creature presents to observers."""

from dataclasses import dataclass
from enum import StrEnum


class ApparentArmorCategory(StrEnum):
    """Classify visible protection without revealing a creature's Armor Class."""

    UNKNOWN = "unknown"
    NONE = "none"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    NATURAL = "natural"
    OTHER = "other"


class ApparentFocusKind(StrEnum):
    """Classify an identifiable spellcasting focus by its visible tradition."""

    NONE = "none"
    ARCANE = "arcane"
    DIVINE = "divine"
    DRUIDIC = "druidic"
    COMPONENT_POUCH = "component_pouch"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ObservableAppearance:
    """Record stable, visually identifiable facts about a creature.

    This is descriptive content, not a second equipment or Armor Class model.
    Ordinary armor, shields, wielded weapons, and foci may inform a player's
    estimate, while exact statistics and hidden or magical properties remain
    outside this value.

    >>> appearance = ObservableAppearance(
    ...     armor_label="Leather Armor",
    ...     armor_category=ApparentArmorCategory.LIGHT,
    ...     visible_weapons=("Scimitar",),
    ... )
    >>> (appearance.armor_category, appearance.visible_weapons)
    (<ApparentArmorCategory.LIGHT: 'light'>, ('Scimitar',))
    """

    armor_label: str | None = None
    armor_category: ApparentArmorCategory = ApparentArmorCategory.UNKNOWN
    has_shield: bool = False
    visible_weapons: tuple[str, ...] = ()
    spellcasting_focus_label: str | None = None
    spellcasting_focus_kind: ApparentFocusKind = ApparentFocusKind.NONE
    obvious_features: tuple[str, ...] = ()
    apparent_creature_type: str | None = None
