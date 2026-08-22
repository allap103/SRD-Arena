from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import Ability, PositiveInt
from .durations import EffectDurationSchema
from .effects import ActionEffectSchema
from .requirements import ActionRequirementSchema

EffectSchemaT = TypeVar("EffectSchemaT")
FailureOutcomeT = TypeVar("FailureOutcomeT")
SuccessOutcomeT = TypeVar("SuccessOutcomeT")


class ResolutionSchemaModel(BaseModel):
    """Validation base for authored executable resolution definitions."""

    model_config = ConfigDict(extra="forbid")


class OutcomeSchema(ResolutionSchemaModel, Generic[EffectSchemaT]):
    """Effects produced by one branch of an executable resolution."""

    effects: list[EffectSchemaT] = Field(default_factory=list)
    end_spell: bool = False


class FixedDifficultyClassSchema(ResolutionSchemaModel):
    type: Literal["fixed"]
    value: int = Field(gt=0)


class DerivedDifficultyClassSchema(ResolutionSchemaModel):
    type: Literal["spell_save_dc", "ten_plus_spell_level"]


DifficultyClassSchema = Annotated[
    FixedDifficultyClassSchema | DerivedDifficultyClassSchema,
    Field(discriminator="type"),
]


class AutomaticResolutionSchema(
    ResolutionSchemaModel,
    Generic[SuccessOutcomeT],
):
    type: Literal["automatic"]
    outcome: SuccessOutcomeT


class SavingThrowResolutionSchema(
    ResolutionSchemaModel,
    Generic[FailureOutcomeT, SuccessOutcomeT],
):
    type: Literal["saving_throw"]
    ability: Ability | None = None
    difficulty: DifficultyClassSchema
    failure: FailureOutcomeT
    success: SuccessOutcomeT
    success_damage: Literal["none", "half"] = "none"
    automatic_success: list[ActionRequirementSchema] = Field(default_factory=list)
    automatic_failure: list[ActionRequirementSchema] = Field(default_factory=list)
    save_modifiers: list[SavingThrowModifierSchema] = Field(default_factory=list)


class SavingThrowModifierSchema(ResolutionSchemaModel):
    type: Literal["roll_modifier"]
    roll: Literal["saving_throw"]
    mode: Literal["advantage", "disadvantage", "add", "subtract"]
    ability: Ability | None = None
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)


class AttackResolutionSchema(
    ResolutionSchemaModel,
    Generic[SuccessOutcomeT],
):
    type: Literal["spell_attack"]
    mode: Literal["melee", "ranged"]
    attacks: PositiveInt = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    hit: SuccessOutcomeT
    miss: SuccessOutcomeT


class FixedAttackResolutionSchema(ResolutionSchemaModel):
    type: Literal["attack"] = "attack"
    attack_modes: list[Literal["melee", "ranged"]] = Field(min_length=1)
    attack_bonus: int
    hit: list[ActionEffectSchema] = Field(min_length=1)


class RepeatResolutionSchemaBase(ResolutionSchemaModel):
    type: Literal["repeat"]
    count: PositiveInt | Literal["spellcasting_modifier", "slot_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ] = "same_or_different"
    simultaneous: bool = False
    propagation_range_feet: PositiveInt | None = None
    cannot_repeat_target: bool = False

    @model_validator(mode="after")
    def validate_propagation(self) -> "RepeatResolutionSchemaBase":
        if self.allocation == "propagating" and self.propagation_range_feet is None:
            raise ValueError("Propagating resolution requires a propagation range.")
        return self


class SequenceResolutionSchemaBase(ResolutionSchemaModel):
    type: Literal["sequence"]


class RepeatSaveProgressionSchemaBase(ResolutionSchemaModel):
    trigger: Literal["turn_start", "turn_end", "source_turn_start", "source_turn_end"]
    ability: Ability | None = None
    successes_required: PositiveInt = 1
    failures_required: PositiveInt | None = None
    counters_need_not_be_consecutive: bool = True
