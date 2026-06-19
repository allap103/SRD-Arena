from pydantic import BaseModel, ConfigDict, Field, model_validator


class ItemRequirementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    quantity: int = 1
    missing_message: str | None = None
    consume: bool = False


class RequirementsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ItemRequirementSchema] = Field(default_factory=list)


class SkillTestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    difficulty: int
    repeatable: bool = True
    effects: "EffectsSchema | None" = None


class OutcomeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = None
    next_scene: str | None = None
    gain_item: str | None = None
    lose_item: str | None = None
    damage: int = 0
    healing: int = 0


class EffectsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_success: OutcomeSchema | None = None
    on_failure: OutcomeSchema | None = None


class SceneChoiceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = None
    next_scene: str | None = None
    requirements: RequirementsSchema | None = None
    test: SkillTestSchema | None = None

    @model_validator(mode="before")
    @classmethod
    def expand_string_shorthand(cls, value):
        if isinstance(value, str):
            return {"next_scene": value}
        return value


class PositionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class GridSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class BehaviorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    anchor: PositionSchema | None = None
    radius: int | None = None
    path: list[PositionSchema] = Field(default_factory=list)


class EncounterEnemySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    start: PositionSchema
    behavior: BehaviorSchema


class EncounterResolutionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_scene: str


class FleeSchema(EncounterResolutionSchema):
    allowed: bool = False


class EncounterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid: GridSchema
    player_start: PositionSchema
    enemies: list[EncounterEnemySchema] = Field(default_factory=list)
    victory: EncounterResolutionSchema
    defeat: EncounterResolutionSchema
    flee: FleeSchema | None = None


class SceneSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "basic"
    text: str
    encounter: EncounterSchema | None = None
    choices: dict[str, SceneChoiceSchema]
