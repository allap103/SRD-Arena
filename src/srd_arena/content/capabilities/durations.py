"""Validate the lifetimes and ending rules of authored effects."""

from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt


class EndOfTurnDurationSchema(CapabilitySchemaModel):
    """Encode the ``end_of_turn`` effect-duration variant with creature."""

    type: Literal["end_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class StartOfTurnDurationSchema(CapabilitySchemaModel):
    """Encode the ``start_of_turn`` effect-duration variant with creature."""

    type: Literal["start_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class TimedDurationSchema(CapabilitySchemaModel):
    """Encode the ``timed`` effect-duration variant with amount and unit."""

    type: Literal["timed"]
    amount: PositiveInt
    unit: Literal["round", "minute", "hour", "day"]


class UntilEventDurationSchema(CapabilitySchemaModel):
    """Encode the ``until_event`` effect-duration variant with events and match."""

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
    """Encode the ``permanent`` effect-duration variant."""

    type: Literal["permanent"]


EffectDurationSchema = Annotated[
    EndOfTurnDurationSchema
    | StartOfTurnDurationSchema
    | TimedDurationSchema
    | UntilEventDurationSchema
    | PermanentDurationSchema,
    Field(discriminator="type"),
]
