"""Validate the ordered rule steps that resolve authored capabilities."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import Ability


class ResolutionSchemaModel(BaseModel):
    """Validation base for authored executable resolution definitions."""

    model_config = ConfigDict(extra="forbid")


class OutcomeSchema[EffectSchemaT](ResolutionSchemaModel):
    """Effects produced by one branch of an executable resolution."""

    effects: list[EffectSchemaT] = Field(default_factory=list)


class FixedDifficultyClassSchema(ResolutionSchemaModel):
    """Encode the ``fixed`` capability-resolution variant with value."""

    type: Literal["fixed"]
    value: int = Field(gt=0)


class DerivedDifficultyClassSchema(ResolutionSchemaModel):
    """Define the authored capability-resolution fields."""

    type: Literal["spell_save_dc", "ten_plus_spell_level"]


DifficultyClassSchema = Annotated[
    FixedDifficultyClassSchema | DerivedDifficultyClassSchema,
    Field(discriminator="type"),
]


class AutomaticResolutionSchema[SuccessOutcomeT](ResolutionSchemaModel):
    """Encode the ``automatic`` capability-resolution variant with outcome."""

    type: Literal["automatic"]
    outcome: SuccessOutcomeT


class SavingThrowResolutionSchema[FailureOutcomeT, SuccessOutcomeT](
    ResolutionSchemaModel
):
    """Encode the ``saving_throw`` capability-resolution variant with ability."""

    type: Literal["saving_throw"]
    ability: Ability | None = None
    difficulty: DifficultyClassSchema
    failure: FailureOutcomeT
    success: SuccessOutcomeT
    success_damage: Literal["none", "half"] = "none"
