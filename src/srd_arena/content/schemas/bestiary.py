import re

from pydantic import Field, model_validator

from .base import SourceModel
from .multiattack import (
    MultiattackMechanicsSchema,
    iter_stat_block_references,
)
from .action_mechanics import NonMultiattackMechanicsSchema

BestiaryActionMechanicsSchema = (
    MultiattackMechanicsSchema | NonMultiattackMechanicsSchema
)


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


class BestiaryConditionalImmunitySchema(SourceModel):
    condition_immune: list[str] = Field(alias="conditionImmune")
    note: str | None = None
    conditional: bool = Field(default=True, alias="cond")


class BestiaryConditionalSpeedSchema(SourceModel):
    number: int
    condition: str | None = None


BestiarySpeedValue = int | BestiaryConditionalSpeedSchema


class BestiarySpeedSchema(SourceModel):
    walk: BestiarySpeedValue | None = None
    burrow: BestiarySpeedValue | None = None
    climb: BestiarySpeedValue | None = None
    fly: BestiarySpeedValue | None = None
    swim: BestiarySpeedValue | None = None
    can_hover: bool = Field(default=False, alias="canHover")
    alternate: dict[str, object] | None = None
    choose: dict[str, object] | None = None

    def feet_for(self, mode: str) -> int | None:
        value = getattr(self, mode, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, BestiaryConditionalSpeedSchema):
            return value.number
        return None


class BestiaryActionSchema(SourceModel):
    name: str
    entries: list[object] = Field(default_factory=list)
    mechanics: BestiaryActionMechanicsSchema | None = Field(
        default=None,
        discriminator="type",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_obsolete_mechanics_key(cls, value: object) -> object:
        if isinstance(value, dict) and "srdArenaMultiattack" in value:
            raise ValueError(
                "Use 'mechanics' instead of the obsolete "
                "'srdArenaMultiattack' key."
            )
        if isinstance(value, dict):
            mechanics = value.get("mechanics")
            if (
                isinstance(mechanics, dict)
                and "type" not in mechanics
                and "plans" in mechanics
            ):
                return {
                    **value,
                    "mechanics": {"type": "multiattack", **mechanics},
                }
        return value


class BestiaryMonsterSchema(SourceModel):
    name: str
    source: str
    size: str | list[str] = "M"
    speed: BestiarySpeedSchema = Field(default_factory=BestiarySpeedSchema)
    hp: BestiaryHitPointsSchema = Field(default_factory=BestiaryHitPointsSchema)
    ac: list[int | BestiaryArmorClassSchema] = Field(default_factory=list)
    action: list[BestiaryActionSchema] = Field(default_factory=list)
    bonus: list[BestiaryActionSchema] = Field(default_factory=list)
    reaction: list[BestiaryActionSchema] = Field(default_factory=list)
    legendary: list[BestiaryActionSchema] = Field(default_factory=list)
    spellcasting: list[BestiaryActionSchema] = Field(default_factory=list)
    type: str | BestiaryTypeSchema | None = None
    alignment: list[str | object] = Field(default_factory=list)
    cr: str | BestiaryChallengeRatingSchema | None = None
    save: dict[str, str] = Field(default_factory=dict)
    skill: dict[str, str] = Field(default_factory=dict)
    senses: list[str] = Field(default_factory=list)
    passive: int | None = None
    languages: list[str] = Field(default_factory=list)
    condition_immune: list[str | BestiaryConditionalImmunitySchema] = Field(
        default_factory=list,
        alias="conditionImmune",
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
        sections = {
            section: {
                _reference_name(entry.name)
                for entry in getattr(self, section)
            }
            for section in (
                "action",
                "bonus",
                "reaction",
                "legendary",
                "spellcasting",
            )
        }
        for action in self.action:
            mechanics = action.mechanics
            if not isinstance(mechanics, MultiattackMechanicsSchema):
                continue
            for section, name in iter_stat_block_references(mechanics):
                if _reference_name(name) not in sections[section]:
                    raise ValueError(
                        f"Multiattack references missing {section} entry "
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


class BestiaryFileSchema(SourceModel):
    monster: list[BestiaryMonsterSchema] = Field(default_factory=list)


def _reference_name(name: str) -> str:
    return re.sub(r"\s*\{@[^}]+\}", "", name).strip().casefold()
