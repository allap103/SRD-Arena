"""Validate scenario order, simulation settings, and presentation metadata."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeometryConfigSchema(BaseModel):
    """Validate scenario-level geometry rule configuration."""

    model_config = ConfigDict(extra="forbid")

    directional_area_cell_coverage_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )


class ScenarioSchema(BaseModel):
    """Validate one authored scenario configuration document.

    >>> ScenarioSchema(display_name="Demo", encounters=["duel"]).encounters
    ('duel',)
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = "Unnamed Scenario"
    encounters: tuple[str, ...] = ("goblin_encounter",)
    background_image: str | None = None
    grid_color: str = "#d3d3d3"
    grid_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    geometry: GeometryConfigSchema = Field(default_factory=GeometryConfigSchema)

    @field_validator("display_name")
    @classmethod
    def require_display_name(cls, value: str) -> str:
        """Strip and require a non-empty scenario display name.

        >>> ScenarioSchema(display_name="  Demo  ").display_name
        'Demo'
        """

        stripped = value.strip()
        if not stripped:
            raise ValueError("A scenario display name must not be empty.")
        return stripped

    @field_validator("encounters")
    @classmethod
    def require_unique_encounters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a non-empty ordered collection of unique encounter IDs.

        >>> from pydantic import ValidationError
        >>> try:
        ...     ScenarioSchema(display_name="Demo", encounters=[])
        ... except ValidationError as error:
        ...     "at least one encounter" in str(error)
        True
        """

        if not value:
            raise ValueError("A scenario must contain at least one encounter.")
        if len(value) != len(set(value)):
            raise ValueError("Scenario encounter IDs must be unique.")
        return value
