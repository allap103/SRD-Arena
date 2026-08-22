from pydantic import Field

from srd_arena.content.common.schema import SourceModel


class ItemPropertySchema(SourceModel):
    uid: str


class ItemSchema(SourceModel):
    name: str
    source: str
    type: str = ""
    entries: list[object] = Field(default_factory=list)
    additional_entries: list[object] = Field(
        default_factory=list,
        alias="additionalEntries",
    )
    weapon: bool = False
    armor: bool = False
    ac: int | None = None
    damage: str | None = Field(default=None, alias="dmg1")
    damage_type: str = Field(default="", alias="dmgType")
    properties: list[str | ItemPropertySchema] = Field(
        default_factory=list,
        alias="property",
    )
    weapon_category: str = Field(default="", alias="weaponCategory")
    range: str | None = None
    misc_tags: list[str] = Field(default_factory=list, alias="miscTags")
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name

    @property
    def is_weapon(self) -> bool:
        return self.weapon or self.damage is not None

    @property
    def is_armor(self) -> bool:
        return self.armor or isinstance(self.ac, int)
