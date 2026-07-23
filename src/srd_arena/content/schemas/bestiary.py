from pydantic import BaseModel, ConfigDict, Field


class BestiarySourceModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class BestiaryHitPointsSchema(BestiarySourceModel):
    average: int | None = None
    formula: str | None = None
    special: str | None = None


class BestiaryArmorClassSchema(BestiarySourceModel):
    ac: int | None = None
    special: str | None = None


class BestiaryActionSchema(BestiarySourceModel):
    name: str
    entries: list[object] = Field(default_factory=list)


class BestiaryMonsterSchema(BestiarySourceModel):
    name: str
    source: str
    size: str | list[str] = "M"
    speed: dict[str, object] = Field(default_factory=dict)
    hp: BestiaryHitPointsSchema = Field(default_factory=BestiaryHitPointsSchema)
    ac: list[int | BestiaryArmorClassSchema] = Field(default_factory=list)
    action: list[BestiaryActionSchema] = Field(default_factory=list)
    strength: int = Field(default=10, alias="str")
    dexterity: int = Field(default=10, alias="dex")
    constitution: int = Field(default=10, alias="con")
    intelligence: int = Field(default=10, alias="int")
    wisdom: int = Field(default=10, alias="wis")
    charisma: int = Field(default=10, alias="cha")
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name

    @property
    def average_hit_points(self) -> int | None:
        return self.hp.average

    @property
    def armor_class(self) -> int | None:
        if not self.ac:
            return None
        first = self.ac[0]
        return first if isinstance(first, int) else first.ac

    @property
    def walk_speed(self) -> int | None:
        walk = self.speed.get("walk")
        return walk if isinstance(walk, int) and not isinstance(walk, bool) else None

    @property
    def primary_size(self) -> str:
        if isinstance(self.size, str):
            return self.size
        return self.size[0] if self.size else "M"


class BestiaryFileSchema(BestiarySourceModel):
    monster: list[BestiaryMonsterSchema] = Field(default_factory=list)
