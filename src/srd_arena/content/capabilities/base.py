from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Ability = Literal["str", "dex", "con", "int", "wis", "cha"]


class CapabilitySchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
