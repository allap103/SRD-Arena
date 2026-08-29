"""Validate the authored forms of intrinsic spell metadata."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class SpellMetadataSchemaModel(BaseModel):
    """Reject unknown keys within executable spell metadata records."""

    model_config = ConfigDict(extra="forbid")


class SpellCastingTimeSchema(SpellMetadataSchemaModel):
    """Validate one authored casting-time option."""

    number: PositiveInt
    unit: Literal["action", "bonus", "reaction", "minute", "hour"]
    condition: str | None = None
    note: str | None = None


class SpellRangeDistanceSchema(SpellMetadataSchemaModel):
    """Validate a numeric or special authored spell distance."""

    type: Literal["feet", "miles", "self", "sight", "touch", "unlimited"]
    amount: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_amount(self) -> SpellRangeDistanceSchema:
        """Require an amount exactly when the distance kind is numeric."""
        numeric = self.type in {"feet", "miles"}
        if numeric and self.amount is None:
            raise ValueError("Numeric spell distances require an amount.")
        if not numeric and self.amount is not None:
            raise ValueError("Special spell distances cannot define an amount.")
        return self


class SpellRangeSchema(SpellMetadataSchemaModel):
    """Validate an authored spell range shape and distance."""

    type: Literal["point", "cone", "cube", "emanation", "line", "sphere"]
    distance: SpellRangeDistanceSchema


class SpellMaterialComponentSchema(SpellMetadataSchemaModel):
    """Validate an authored priced or consumed material component."""

    text: str = Field(min_length=1)
    cost: PositiveInt | None = None
    consume: bool = False


class SpellComponentsSchema(SpellMetadataSchemaModel):
    """Validate authored verbal, somatic, and material components."""

    v: bool = False
    s: bool = False
    m: str | SpellMaterialComponentSchema | None = None


class SpellDurationAmountSchema(SpellMetadataSchemaModel):
    """Validate the quantity nested within a timed spell duration."""

    type: Literal["round", "minute", "hour", "day"]
    amount: PositiveInt


class SpellDurationSchema(SpellMetadataSchemaModel):
    """Validate one authored instant, permanent, special, or timed duration."""

    type: Literal["instant", "permanent", "special", "timed"]
    concentration: bool = False
    duration: SpellDurationAmountSchema | None = None
    ends: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_variant_fields(self) -> SpellDurationSchema:
        """Require timing and ending fields only on their matching variants."""
        if self.type == "timed" and self.duration is None:
            raise ValueError("Timed spell durations require duration details.")
        if self.type != "timed" and self.duration is not None:
            raise ValueError("Only timed spell durations can define duration details.")
        if self.concentration and self.type != "timed":
            raise ValueError("Only timed spell durations can require concentration.")
        if self.ends and self.type != "permanent":
            raise ValueError("Only permanent spell durations can define ending events.")
        return self
