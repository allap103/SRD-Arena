from pydantic import BaseModel, ConfigDict


class SpellCapabilitySchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
