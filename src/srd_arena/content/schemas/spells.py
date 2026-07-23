from pydantic import Field

from .bestiary import BestiarySourceModel


class SpellSchema(BestiarySourceModel):
    name: str
    source: str
    level: int
    school: str
    time: list[dict[str, object]] = Field(default_factory=list)
    range: dict[str, object] = Field(default_factory=dict)
    components: dict[str, object] = Field(default_factory=dict)
    duration: list[dict[str, object]] = Field(default_factory=list)
    entries: list[object] = Field(default_factory=list)
    saving_throw: list[str] = Field(default_factory=list, alias="savingThrow")
    condition_inflict: list[str] = Field(default_factory=list, alias="conditionInflict")
    damage_inflict: list[str] = Field(default_factory=list, alias="damageInflict")
    area_tags: list[str] = Field(default_factory=list, alias="areaTags")
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class SpellFileSchema(BestiarySourceModel):
    spell: list[SpellSchema] = Field(default_factory=list)
