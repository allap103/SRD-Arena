"""Validate authored optional class-feature selections and effects."""

from pydantic import Field

from srd_arena.content.common.schema import SourceModel


class OptionalFeatureSchema(SourceModel):
    """Define the authored optional-feature fields with name and source."""

    name: str
    source: str
    feature_types: list[str] = Field(default_factory=list, alias="featureType")
    entries: list[object] = Field(default_factory=list)
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        """Return the SRD-facing optional-feature name.

        >>> OptionalFeatureSchema(name="Legacy Invocation", source="X", srd52="Invocation").public_name
        'Invocation'
        """
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class OptionalFeatureFileSchema(SourceModel):
    """Define the authored optional-feature fields with optional features."""

    optional_features: list[OptionalFeatureSchema] = Field(
        default_factory=list,
        alias="optionalfeature",
    )
