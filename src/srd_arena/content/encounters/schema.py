"""Validate authored maps, teams, participants, and encounter behavior."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srd_arena.content.creatures.schema import CreatureSchema


class PositionSchema(BaseModel):
    """Validate one participant's integer grid coordinates."""

    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class GridSchema(BaseModel):
    """Validate positive battlefield dimensions for an encounter."""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class GeometryConfigSchema(BaseModel):
    """Validate encounter-level geometry rule configuration."""

    model_config = ConfigDict(extra="forbid")

    directional_area_cell_coverage_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )


class EncounterConfigSchema(BaseModel):
    """Validate one selectable encounter's metadata and presentation settings."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = "Unnamed Encounter"
    background_image: str | None = None
    grid_color: str = "#d3d3d3"
    grid_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    geometry: GeometryConfigSchema = Field(default_factory=GeometryConfigSchema)

    @model_validator(mode="after")
    def require_display_name(self) -> EncounterConfigSchema:
        """Strip and require a non-empty encounter display name."""

        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("An encounter display name must not be empty.")
        return self


class BehaviorSchema(BaseModel):
    """Validate parameters for an automatically controlled participant policy."""

    model_config = ConfigDict(extra="forbid")

    type: str
    anchor: PositionSchema | None = None
    radius: int | None = None
    path: list[PositionSchema] = Field(default_factory=list)


class EncounterCreatureSchema(CreatureSchema):
    """Define the authored encounter fields with start and team id."""

    model_config = ConfigDict(extra="forbid")

    start: PositionSchema
    team_id: str
    controller: Literal["external", "scripted"] | None = None
    behavior: BehaviorSchema | None = None
    takes_turns: bool = True


class EncounterTeamSchema(BaseModel):
    """Define the authored encounter fields with id and name."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    controller: Literal["external", "scripted"]


class EncounterDefinitionSchema(BaseModel):
    """Define the authored encounter fields with id and grid."""

    model_config = ConfigDict(extra="forbid")

    id: str
    grid: GridSchema
    creatures: list[EncounterCreatureSchema] = Field(default_factory=list)
    teams: list[EncounterTeamSchema] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_creatures(self) -> EncounterDefinitionSchema:
        """Require valid creature identities, turn ownership, and placement.

        >>> from pydantic import ValidationError
        >>> creature = {"id": "hero", "start": {"x": 0, "y": 0}, "team_id": "heroes"}
        >>> try:
        ...     EncounterDefinitionSchema(id="test", grid={"width": 5, "height": 5},
        ...         creatures=[creature, creature])
        ... except ValidationError as error:
        ...     "IDs must be unique" in str(error)
        True
        """
        creature_ids = [creature.id for creature in self.creatures]
        duplicate_ids = sorted(
            creature_id
            for creature_id in set(creature_ids)
            if creature_ids.count(creature_id) > 1
        )
        if duplicate_ids:
            raise ValueError(
                "Encounter creature IDs must be unique: " + ", ".join(duplicate_ids)
            )
        if self.creatures and not any(
            creature.takes_turns for creature in self.creatures
        ):
            raise ValueError("An encounter requires at least one turn-taking creature.")

        outside_grid = [
            creature
            for creature in self.creatures
            if not (
                0 <= creature.start.x < self.grid.width
                and 0 <= creature.start.y < self.grid.height
            )
        ]
        if outside_grid:
            placements = ", ".join(
                f"{creature.id} at ({creature.start.x}, {creature.start.y})"
                for creature in outside_grid
            )
            raise ValueError(
                "Encounter creature starting positions must lie within the grid: "
                + placements
            )

        creature_ids_by_start: dict[tuple[int, int], list[str]] = {}
        for creature in self.creatures:
            position = (creature.start.x, creature.start.y)
            creature_ids_by_start.setdefault(position, []).append(creature.id)
        overlapping_starts = {
            position: creature_ids
            for position, creature_ids in creature_ids_by_start.items()
            if len(creature_ids) > 1
        }
        if overlapping_starts:
            placements = "; ".join(
                f"({x}, {y}): {', '.join(creature_ids)}"
                for (x, y), creature_ids in sorted(overlapping_starts.items())
            )
            raise ValueError(
                "Encounter creature starting positions must be unique: " + placements
            )
        return self


EncounterDefinitionSchema.model_rebuild()
