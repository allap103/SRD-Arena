"""Validate authored monster stat-block sections and action entries."""

import re

from pydantic import Field, model_validator

from srd_arena.content.common.schema import SourceModel

from .actions.multiattack import (
    MultiattackCapabilitySchema,
    iter_stat_block_references,
)
from .actions.schema import NonMultiattackCapabilitySchema

BestiaryCapabilitySchema = MultiattackCapabilitySchema | NonMultiattackCapabilitySchema


class BestiaryHitPointsSchema(SourceModel):
    """Define the authored stat-block fields with average and formula."""

    average: int | None = None
    formula: str | None = None
    special: str | None = None


class BestiaryArmorClassSchema(SourceModel):
    """Define the authored stat-block fields with ac and special."""

    ac: int | None = None
    special: str | None = None


class BestiaryTypeChoiceSchema(SourceModel):
    """Define the authored stat-block fields with choose."""

    choose: list[str] = Field(default_factory=list)


class BestiaryTypeSchema(SourceModel):
    """Define the authored stat-block fields with type and tags."""

    type: str | BestiaryTypeChoiceSchema
    tags: list[str | object] = Field(default_factory=list)


class BestiaryChallengeRatingSchema(SourceModel):
    """Define the authored stat-block fields with cr."""

    cr: str


class BestiaryConditionalImmunitySchema(SourceModel):
    """Define the authored stat-block fields with condition immune and note."""

    condition_immune: list[str] = Field(alias="conditionImmune")
    note: str | None = None
    conditional: bool = Field(default=True, alias="cond")


class BestiaryConditionalSpeedSchema(SourceModel):
    """Define the authored stat-block fields with number and condition."""

    number: int
    condition: str | None = None


BestiarySpeedValue = int | BestiaryConditionalSpeedSchema


class BestiarySpeedSchema(SourceModel):
    """Define the authored stat-block fields with walk and burrow."""

    walk: BestiarySpeedValue | None = None
    burrow: BestiarySpeedValue | None = None
    climb: BestiarySpeedValue | None = None
    fly: BestiarySpeedValue | None = None
    swim: BestiarySpeedValue | None = None
    can_hover: bool = Field(default=False, alias="canHover")
    alternate: dict[str, object] | None = None
    choose: dict[str, object] | None = None

    def feet_for(self, mode: str) -> int | None:
        """Return an unconditional or conditional speed as feet.

        >>> BestiarySpeedSchema(walk=30).feet_for("walk")
        30
        >>> BestiarySpeedSchema(fly={"number": 60, "condition": "while airborne"}).feet_for("fly")
        60
        """
        value = getattr(self, mode, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, BestiaryConditionalSpeedSchema):
            return value.number
        return None


class BestiaryActionSchema(SourceModel):
    """Define the authored stat-block fields with name and entries."""

    name: str
    entries: list[object] = Field(default_factory=list)
    capability: BestiaryCapabilitySchema | None = Field(
        default=None,
        discriminator="type",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_multiattack_key(cls, value: object) -> object:
        """Reject the obsolete pre-capability multiattack extension.

        >>> from pydantic import ValidationError
        >>> try:
        ...     BestiaryActionSchema.model_validate({"name": "Multiattack", "srdArenaMultiattack": {}})
        ... except ValidationError as error:
        ...     "obsolete" in str(error)
        True
        """
        if isinstance(value, dict) and "srdArenaMultiattack" in value:
            raise ValueError(
                "Use 'capability' instead of the obsolete 'srdArenaMultiattack' key."
            )
        return value


class BestiaryMonsterSchema(SourceModel):
    """Define the authored stat-block fields with name and source."""

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
    def validate_multiattack_references(self) -> BestiaryMonsterSchema:
        """Require every multiattack invocation to reference a declared entry.

        >>> from pydantic import ValidationError
        >>> multiattack = {"name": "Multiattack", "capability": {
        ...     "type": "multiattack", "plans": [{"steps": [{"type": "invoke",
        ...     "invocation": {"type": "stat_block_action", "name": "Bite"}}]}]}}
        >>> try:
        ...     BestiaryMonsterSchema(name="Wolf", source="X", action=[multiattack])
        ... except ValidationError as error:
        ...     "missing action entry 'Bite'" in str(error)
        True
        """
        sections = {
            section: {_reference_name(entry.name) for entry in getattr(self, section)}
            for section in (
                "action",
                "bonus",
                "reaction",
                "legendary",
                "spellcasting",
            )
        }
        for action in self.action:
            capability = action.capability
            if not isinstance(capability, MultiattackCapabilitySchema):
                continue
            for section, name in iter_stat_block_references(capability):
                if _reference_name(name) not in sections[section]:
                    raise ValueError(
                        f"Multiattack references missing {section} entry "
                        f"'{name}' on '{self.public_name}'."
                    )
        return self

    @property
    def public_name(self) -> str:
        """Return the SRD-facing monster name.

        >>> BestiaryMonsterSchema(name="Legacy Goblin", source="X", srd52="Goblin").public_name
        'Goblin'
        """
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name

    @property
    def average_hit_points(self) -> int | None:
        """Return authored average hit points when available.

        >>> BestiaryMonsterSchema(name="Goblin", source="X", hp={"average": 7}).average_hit_points
        7
        """
        return self.hp.average

    @property
    def armor_class(self) -> int | None:
        """Return the first authored armor-class value.

        >>> BestiaryMonsterSchema(name="Goblin", source="X", ac=[15]).armor_class
        15
        """
        if not self.ac:
            return None
        first = self.ac[0]
        return first if isinstance(first, int) else first.ac

    @property
    def walk_speed(self) -> int | None:
        """Return the monster's walking speed in feet.

        >>> BestiaryMonsterSchema(name="Goblin", source="X", speed={"walk": 30}).walk_speed
        30
        """
        return self.speed.feet_for("walk")

    @property
    def primary_size(self) -> str:
        """Return the first authored size code.

        >>> BestiaryMonsterSchema(name="Shapechanger", source="X", size=["M", "L"]).primary_size
        'M'
        """
        if isinstance(self.size, str):
            return self.size
        return self.size[0] if self.size else "M"

    @property
    def creature_type(self) -> str | None:
        """Return the base creature type from either authored representation.

        >>> BestiaryMonsterSchema(name="Goblin", source="X", type="humanoid").creature_type
        'humanoid'
        """
        if isinstance(self.type, str):
            return self.type
        if self.type is None or not isinstance(self.type.type, str):
            return None
        return self.type.type

    @property
    def type_tags(self) -> tuple[str, ...]:
        """Return textual subtype tags from a structured creature type.

        >>> monster = BestiaryMonsterSchema(name="Goblin", source="X", type={"type": "humanoid", "tags": ["goblinoid"]})
        >>> monster.type_tags
        ('goblinoid',)
        """
        if not isinstance(self.type, BestiaryTypeSchema):
            return ()
        return tuple(tag for tag in self.type.tags if isinstance(tag, str))

    @property
    def challenge_rating(self) -> str | None:
        """Return challenge rating from either authored representation.

        >>> BestiaryMonsterSchema(name="Goblin", source="X", cr={"cr": "1/4"}).challenge_rating
        '1/4'
        """
        if isinstance(self.cr, str):
            return self.cr
        return self.cr.cr if self.cr is not None else None


class BestiaryFileSchema(SourceModel):
    """Define the authored stat-block fields with monster."""

    monster: list[BestiaryMonsterSchema] = Field(default_factory=list)


def _reference_name(name: str) -> str:
    return re.sub(r"\s*\{@[^}]+\}", "", name).strip().casefold()
