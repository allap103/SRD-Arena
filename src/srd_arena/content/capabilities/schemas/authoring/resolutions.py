"""Recursive schemas for executable capability resolutions."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, RootModel

from srd_arena.content.capabilities.schemas.base import Ability, CapabilitySchemaModel
from srd_arena.content.capabilities.schemas.effects import ActionEffectSchema
from srd_arena.content.capabilities.schemas.resolutions import (
    AttackResolutionSchema as SharedAttackResolutionSchema,
    AutomaticResolutionSchema as SharedAutomaticResolutionSchema,
    DerivedDifficultyClassSchema,
    OutcomeSchema as SharedOutcomeSchema,
    RepeatResolutionSchemaBase,
    RepeatSaveProgressionSchemaBase,
    SavingThrowResolutionSchema as SharedSavingThrowResolutionSchema,
    SequenceResolutionSchemaBase,
)
from srd_arena.content.capabilities.schemas.targets import ExecutableTargetSchema


class CapabilityEffectSchema(RootModel[ActionEffectSchema]):
    """One effect supported by the capability runtime."""


class OutcomeSchema(SharedOutcomeSchema[CapabilityEffectSchema]):
    """An executable capability outcome."""


class AutomaticResolutionSchema(SharedAutomaticResolutionSchema[OutcomeSchema]):
    """An outcome that applies without a roll."""


class SavingThrowResolutionSchema(
    SharedSavingThrowResolutionSchema[OutcomeSchema, OutcomeSchema]
):
    """A saving throw with optional repeated saves."""

    ability: Ability
    difficulty: DerivedDifficultyClassSchema = Field(
        default_factory=lambda: DerivedDifficultyClassSchema(type="provider_save_dc")
    )
    success: OutcomeSchema = Field(default_factory=OutcomeSchema)
    repeat_save: RepeatSaveProgressionSchema | None = None


class DerivedAttackResolutionSchema(SharedAttackResolutionSchema[OutcomeSchema]):
    """An attack using the capability provider's attack modifier."""

    miss: OutcomeSchema = Field(default_factory=OutcomeSchema)


class RepeatResolutionSchema(RepeatResolutionSchemaBase):
    """Repeat a nested executable resolution."""

    resolution: CapabilityResolutionSchema


class SequenceStepSchema(CapabilitySchemaModel):
    """One resolution and optional target in an ordered sequence."""

    resolution: CapabilityResolutionSchema
    target: ExecutableTargetSchema | None = None


class SequenceResolutionSchema(SequenceResolutionSchemaBase):
    """Execute multiple resolution steps in order."""

    steps: list[SequenceStepSchema] = Field(min_length=1)


class CapabilityResolutionSchema(
    RootModel[
        Annotated[
            AutomaticResolutionSchema
            | SavingThrowResolutionSchema
            | DerivedAttackResolutionSchema
            | RepeatResolutionSchema
            | SequenceResolutionSchema,
            Field(discriminator="type"),
        ]
    ]
):
    """One resolution supported by the capability runtime."""


class RepeatSaveProgressionSchema(RepeatSaveProgressionSchemaBase):
    """A repeated saving throw applied after an initial failed save."""

    on_success: CapabilityResolutionSchema = Field(
        default_factory=lambda: CapabilityResolutionSchema.model_validate(
            {"type": "automatic", "outcome": {"end_capability": True}}
        )
    )
    on_failure: CapabilityResolutionSchema | None = None


RepeatResolutionSchema.model_rebuild()
SequenceStepSchema.model_rebuild()
SequenceResolutionSchema.model_rebuild()
CapabilityResolutionSchema.model_rebuild()
RepeatSaveProgressionSchema.model_rebuild()
