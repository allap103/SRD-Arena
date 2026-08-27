"""Provide optional feature schema support for the classes package."""

from pydantic import Field

from srd_arena.content.common.schema import SourceModel


class OptionalFeatureSchema(SourceModel):
    """Validate authored optional feature data."""

    name: str
    source: str
    feature_types: list[str] = Field(default_factory=list, alias="featureType")
    entries: list[object] = Field(default_factory=list)
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class OptionalFeatureFileSchema(SourceModel):
    """Validate authored optional feature file data."""

    optional_features: list[OptionalFeatureSchema] = Field(
        default_factory=list,
        alias="optionalfeature",
    )
