from pydantic import Field, model_validator

from .base import SourceModel
from .spell_mechanics import SpellImplementationSchema, SpellMechanicsSchema


class SpellSchema(SourceModel):
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
    affects_creature_type: list[str] = Field(
        default_factory=list,
        alias="affectsCreatureType",
    )
    implementation: SpellImplementationSchema = Field(
        default_factory=SpellImplementationSchema
    )
    mechanics: SpellMechanicsSchema | None = None
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @model_validator(mode="after")
    def validate_implementation_state(self) -> "SpellSchema":
        status = self.implementation.status
        if status in {"complete", "partial", "blocked"} and self.mechanics is None:
            raise ValueError(f"{status.title()} spells must define mechanics.")
        if status in {"unimplemented", "out_of_scope"} and self.mechanics is not None:
            raise ValueError(f"{status.title()} spells cannot define mechanics.")
        return self

    @property
    def executable(self) -> bool:
        return self.mechanics is not None and self.implementation.status in {
            "complete",
            "partial",
        }

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class SpellFileSchema(SourceModel):
    spell: list[SpellSchema] = Field(default_factory=list)
