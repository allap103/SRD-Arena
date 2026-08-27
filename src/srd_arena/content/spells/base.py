"""Provide base support for the spells package."""

from pydantic import BaseModel, ConfigDict


class SpellCapabilitySchemaModel(BaseModel):
    """Represent a spell capability schema model."""

    model_config = ConfigDict(extra="forbid")
