"""Define strict validation conventions shared by authored capabilities."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Ability = Literal["str", "dex", "con", "int", "wis", "cha"]


class CapabilitySchemaModel(BaseModel):
    """Reject unknown fields in every authored capability schema model.

    Strict models keep misspelled or obsolete rules data from silently entering
    the domain translation layer.
    """

    model_config = ConfigDict(extra="forbid")
