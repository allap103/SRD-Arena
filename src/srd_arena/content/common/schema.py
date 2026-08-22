from pydantic import BaseModel, ConfigDict


class SourceModel(BaseModel):
    """Typed view of source fields consumed by the application."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
