from pydantic import Field

from .base import SourceModel


class BestiaryHitPointsSchema(SourceModel):
    average: int | None = None
    formula: str | None = None
    special: str | None = None


class BestiaryArmorClassSchema(SourceModel):
    ac: int | None = None
    special: str | None = None


class BestiaryTypeChoiceSchema(SourceModel):
    choose: list[str] = Field(default_factory=list)


class BestiaryTypeSchema(SourceModel):
    type: str | BestiaryTypeChoiceSchema
    tags: list[str | object] = Field(default_factory=list)


class BestiaryChallengeRatingSchema(SourceModel):
    cr: str


class BestiaryActionSchema(SourceModel):
    name: str
    entries: list[object] = Field(default_factory=list)


class BestiaryMonsterSchema(SourceModel):
    name: str
    source: str
    size: str | list[str] = "M"
    speed: dict[str, object] = Field(default_factory=dict)
    hp: BestiaryHitPointsSchema = Field(default_factory=BestiaryHitPointsSchema)
    ac: list[int | BestiaryArmorClassSchema] = Field(default_factory=list)
    action: list[BestiaryActionSchema] = Field(default_factory=list)
    type: str | BestiaryTypeSchema | None = None
    alignment: list[str | object] = Field(default_factory=list)
    cr: str | BestiaryChallengeRatingSchema | None = None
    save: dict[str, str] = Field(default_factory=dict)
    skill: dict[str, str] = Field(default_factory=dict)
    senses: list[str] = Field(default_factory=list)
    passive: int | None = None
    languages: list[str] = Field(default_factory=list)
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

    @property
    def creature_type(self) -> str | None:
        if isinstance(self.type, str):
            return self.type
        if self.type is None or not isinstance(self.type.type, str):
            return None
        return self.type.type

    @property
    def type_tags(self) -> tuple[str, ...]:
        if not isinstance(self.type, BestiaryTypeSchema):
            return ()
        return tuple(tag for tag in self.type.tags if isinstance(tag, str))

    @property
    def challenge_rating(self) -> str | None:
        if isinstance(self.cr, str):
            return self.cr
        return self.cr.cr if self.cr is not None else None


class BestiaryFileSchema(SourceModel):
    monster: list[BestiaryMonsterSchema] = Field(default_factory=list)
