from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .base import Ability

EffectSchemaT = TypeVar("EffectSchemaT")
FailureOutcomeT = TypeVar("FailureOutcomeT")
SuccessOutcomeT = TypeVar("SuccessOutcomeT")


class ResolutionSchemaModel(BaseModel):
    """Validation base for authored executable resolution definitions."""

    model_config = ConfigDict(extra="forbid")


class OutcomeSchema(ResolutionSchemaModel, Generic[EffectSchemaT]):
    """Effects produced by one branch of an executable resolution."""

    effects: list[EffectSchemaT] = Field(default_factory=list)


class FixedDifficultyClassSchema(ResolutionSchemaModel):
    type: Literal["fixed"]
    value: int = Field(gt=0)


class DerivedDifficultyClassSchema(ResolutionSchemaModel):
    type: Literal["spell_save_dc", "ten_plus_spell_level"]


DifficultyClassSchema = Annotated[
    FixedDifficultyClassSchema | DerivedDifficultyClassSchema,
    Field(discriminator="type"),
]


class AutomaticResolutionSchema(
    ResolutionSchemaModel,
    Generic[SuccessOutcomeT],
):
    type: Literal["automatic"]
    outcome: SuccessOutcomeT


class SavingThrowResolutionSchema(
    ResolutionSchemaModel,
    Generic[FailureOutcomeT, SuccessOutcomeT],
):
    type: Literal["saving_throw"]
    ability: Ability | None = None
    difficulty: DifficultyClassSchema
    failure: FailureOutcomeT
    success: SuccessOutcomeT
    success_damage: Literal["none", "half"] = "none"
