"""Provide schema support for the common package."""

from pydantic import BaseModel, ConfigDict


class SourceModel(BaseModel):
    """Typed view of a source record that preserves unmodeled source data."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
