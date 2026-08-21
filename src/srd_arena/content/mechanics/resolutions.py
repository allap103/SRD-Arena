from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

EffectSchemaT = TypeVar("EffectSchemaT")


class ResolutionSchemaModel(BaseModel):
    """Validation base for authored executable resolution definitions."""

    model_config = ConfigDict(extra="forbid")


class OutcomeSchema(ResolutionSchemaModel, Generic[EffectSchemaT]):
    """Effects produced by one branch of an executable resolution."""

    effects: list[EffectSchemaT] = Field(default_factory=list)
