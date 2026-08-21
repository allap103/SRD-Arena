from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt


class EndOfTurnDurationSchema(CapabilitySchemaModel):
    type: Literal["end_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class StartOfTurnDurationSchema(CapabilitySchemaModel):
    type: Literal["start_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class TimedDurationSchema(CapabilitySchemaModel):
    type: Literal["timed"]
    amount: PositiveInt
    unit: Literal["round", "minute", "hour", "day"]


class UntilEventDurationSchema(CapabilitySchemaModel):
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
    type: Literal["permanent"]


EffectDurationSchema = Annotated[
    EndOfTurnDurationSchema
    | StartOfTurnDurationSchema
    | TimedDurationSchema
    | UntilEventDurationSchema
    | PermanentDurationSchema,
    Field(discriminator="type"),
]
