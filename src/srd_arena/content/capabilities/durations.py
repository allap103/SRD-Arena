"""Provide durations support for the capabilities package."""

from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt


class EndOfTurnDurationSchema(CapabilitySchemaModel):
    """Validate authored end of turn duration data."""

    type: Literal["end_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class StartOfTurnDurationSchema(CapabilitySchemaModel):
    """Validate authored start of turn duration data."""

    type: Literal["start_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class TimedDurationSchema(CapabilitySchemaModel):
    """Validate authored timed duration data."""

    type: Literal["timed"]
    amount: PositiveInt
    unit: Literal["round", "minute", "hour", "day"]


class UntilEventDurationSchema(CapabilitySchemaModel):
    """Validate authored until event duration data."""

    type: Literal["until_event"]
    events: list[
        Literal[
            "source_dies",
            "different_plane",
            "target_takes_damage",
            "adjacent_creature_wakes_target",
        ]
    ] = Field(min_length=1)
    match: Literal["any", "all"] = "any"


class PermanentDurationSchema(CapabilitySchemaModel):
    """Validate authored permanent duration data."""

    type: Literal["permanent"]


EffectDurationSchema = Annotated[
    EndOfTurnDurationSchema
    | StartOfTurnDurationSchema
    | TimedDurationSchema
    | UntilEventDurationSchema
    | PermanentDurationSchema,
    Field(discriminator="type"),
]
