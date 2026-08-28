"""Define strict validation conventions for spell-authored rule fragments."""

from pydantic import BaseModel, ConfigDict


class SpellCapabilitySchemaModel(BaseModel):
    """Reject unknown fields in spell-specific authored schema models."""

    model_config = ConfigDict(extra="forbid")
