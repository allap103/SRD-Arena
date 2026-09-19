"""Validate authored equipment statistics and granted capabilities."""

from pydantic import Field

from srd_arena.content.common.schema import SourceModel


class ItemPropertySchema(SourceModel):
    """Define the authored equipment fields with uid and note."""

    uid: str
    note: str | None = None


class ItemSchema(SourceModel):
    """Validate an item's identity and optional weapon or armor statistics."""

    name: str
    source: str
    type: str = ""
    entries: list[object] = Field(default_factory=list)
    additional_entries: list[object] = Field(
        default_factory=list,
        alias="additionalEntries",
    )
    weapon: bool = False
    damage: str | None = Field(default=None, alias="dmg1")
    damage_type: str = Field(default="", alias="dmgType")
    properties: list[str | ItemPropertySchema] = Field(
        default_factory=list,
        alias="property",
    )
    mastery: list[str] = Field(default_factory=list)
    weapon_category: str = Field(default="", alias="weaponCategory")
    range: str | None = None
    armor: bool = False
    armor_class: int | None = Field(default=None, alias="ac")
    strength_requirement: str | int | None = Field(default=None, alias="strength")
    stealth_disadvantage: bool = Field(default=False, alias="stealth")
    misc_tags: list[str] = Field(default_factory=list, alias="miscTags")
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        """Return the SRD-facing name when the source provides one.

        >>> ItemSchema(name="Longsword Legacy", source="X", srd52="Longsword").public_name
        'Longsword'
        """
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name

    @property
    def is_weapon(self) -> bool:
        """Return whether authored fields identify this item as a weapon.

        >>> ItemSchema(name="Longsword", source="X", dmg1="1d8").is_weapon
        True
        """
        return self.weapon or self.damage is not None

    @property
    def is_armor(self) -> bool:
        """Return whether authored fields identify armor or a Shield.

        >>> ItemSchema(name="Leather Armor", source="X", type="LA", ac=11).is_armor
        True
        >>> ItemSchema(name="Shield", source="X", type="S", ac=2).is_armor
        True
        """

        return self.armor or self.type.split("|", 1)[0] in {"LA", "MA", "HA", "S"}
