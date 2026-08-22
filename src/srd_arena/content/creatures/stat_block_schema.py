import re

from pydantic import Field, model_validator

from srd_arena.content.common.schema import SourceModel
from .actions.multiattack import (
    MultiattackCapabilitySchema,
    iter_action_references,
)
from .actions.schema import NonMultiattackCapabilitySchema

BestiaryCapabilitySchema = MultiattackCapabilitySchema | NonMultiattackCapabilitySchema


class BestiaryHitPointsSchema(SourceModel):
    average: int | None = None


class BestiaryArmorClassSchema(SourceModel):
    ac: int | None = None


class BestiaryTypeSchema(SourceModel):
    type: str | dict[str, object]
    tags: list[str | object] = Field(default_factory=list)


class BestiaryChallengeRatingSchema(SourceModel):
    cr: str


class BestiaryConditionalSpeedSchema(SourceModel):
    number: int


BestiarySpeedValue = int | BestiaryConditionalSpeedSchema


class BestiarySpeedSchema(SourceModel):
    walk: BestiarySpeedValue | None = None
    burrow: BestiarySpeedValue | None = None
    climb: BestiarySpeedValue | None = None
    fly: BestiarySpeedValue | None = None
    swim: BestiarySpeedValue | None = None

    def feet_for(self, mode: str) -> int | None:
        value = getattr(self, mode, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, BestiaryConditionalSpeedSchema):
            return value.number
        return None


class BestiaryActionSummarySchema(SourceModel):
    """Source text required to present a stat-block action."""

    name: str
    entries: list[object] = Field(default_factory=list)


class BestiaryActionSchema(BestiaryActionSummarySchema):
    """An ordinary action with an optional executable capability."""

    capability: BestiaryCapabilitySchema | None = Field(
        default=None,
        discriminator="type",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_multiattack_key(cls, value: object) -> object:
        if isinstance(value, dict) and "srdArenaMultiattack" in value:
            raise ValueError(
                "Use 'capability' instead of the obsolete 'srdArenaMultiattack' key."
            )
        return value


class BestiaryMonsterSchema(SourceModel):
    """Runtime-relevant fields from an imported monster record."""

    name: str
    source: str
    size: str | list[str] = "M"
    speed: BestiarySpeedSchema = Field(default_factory=BestiarySpeedSchema)
    hp: BestiaryHitPointsSchema = Field(default_factory=BestiaryHitPointsSchema)
    ac: list[int | BestiaryArmorClassSchema] = Field(default_factory=list)
    action: list[BestiaryActionSchema] = Field(default_factory=list)
    bonus: list[BestiaryActionSummarySchema] = Field(default_factory=list)
    type: str | BestiaryTypeSchema | None = None
    alignment: list[str | object] = Field(default_factory=list)
    cr: str | BestiaryChallengeRatingSchema | None = None
    save: dict[str, str] = Field(default_factory=dict)
    skill: dict[str, str] = Field(default_factory=dict)
    senses: list[str] = Field(default_factory=list)
    passive: int | None = None
    languages: list[str] = Field(default_factory=list)
    condition_immune: list[str | dict[str, object]] = Field(
        default_factory=list,
        alias="conditionImmune",
    )
    mechanical_traits: list[str] = Field(
        default_factory=list,
        alias="mechanicalTraits",
    )
    strength: int = Field(default=10, alias="str")
    dexterity: int = Field(default=10, alias="dex")
    constitution: int = Field(default=10, alias="con")
    intelligence: int = Field(default=10, alias="int")
    wisdom: int = Field(default=10, alias="wis")
    charisma: int = Field(default=10, alias="cha")
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @model_validator(mode="after")
    def validate_multiattack_references(self) -> "BestiaryMonsterSchema":
        action_names = {_reference_name(entry.name) for entry in self.action}
        for action in self.action:
            capability = action.capability
            if not isinstance(capability, MultiattackCapabilitySchema):
                continue
            for name in iter_action_references(capability):
                if _reference_name(name) not in action_names:
                    raise ValueError(
                        "Multiattack references missing action entry "
                        f"'{name}' on '{self.public_name}'."
                    )
        return self

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
        return self.speed.feet_for("walk")

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


def _reference_name(name: str) -> str:
    return re.sub(r"\s*\{@[^}]+\}", "", name).strip().casefold()
