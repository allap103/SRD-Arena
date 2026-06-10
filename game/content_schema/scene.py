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
    gain_item: str | None = None
    lose_item: str | None = None


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


class SceneSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "basic"
    text: str
    choices: dict[str, SceneChoiceSchema]
