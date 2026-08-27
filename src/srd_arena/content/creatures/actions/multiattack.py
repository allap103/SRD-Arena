"""Provide multiattack support for the actions package."""

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srd_arena.domain.creatures import (
    Multiattack,
    MultiattackCount,
    MultiattackInvocation,
    MultiattackPlan,
    MultiattackReplacement,
    MultiattackRequirement,
    MultiattackStep,
)

PositiveInt = Annotated[int, Field(gt=0)]
StatBlockSection = Literal[
    "action",
    "bonus",
    "reaction",
    "legendary",
    "spellcasting",
]


class MultiattackSchemaModel(BaseModel):
    """Represent a multiattack schema model."""

    model_config = ConfigDict(extra="forbid")


class CreatureStatCountSchema(MultiattackSchemaModel):
    """Validate authored creature stat count data."""

    type: Literal["creature_stat"]
    stat: str = Field(min_length=1)


class HalfSpellLevelCountSchema(MultiattackSchemaModel):
    """Validate authored half spell level count data."""

    type: Literal["half_spell_level"]
    round: Literal["down", "up"] = "down"


DynamicCountSchema = Annotated[
    CreatureStatCountSchema | HalfSpellLevelCountSchema,
    Field(discriminator="type"),
]
RepeatCountSchema = PositiveInt | DynamicCountSchema


class ActionUsedThisTurnRequirementSchema(MultiattackSchemaModel):
    """Validate authored action used this turn requirement data."""

    type: Literal["action_used_this_turn"]
    action: str = Field(min_length=1)


class SpellReferenceSchema(MultiattackSchemaModel):
    """Validate authored spell reference data."""

    name: str = Field(min_length=1)
    source: str | None = None


class StatBlockActionInvocationSchema(MultiattackSchemaModel):
    """Validate authored stat block action invocation data."""

    type: Literal["stat_block_action"]
    name: str = Field(min_length=1)
    section: StatBlockSection = "action"


class CastSpellInvocationSchema(MultiattackSchemaModel):
    """Validate authored cast spell invocation data."""

    type: Literal["cast_spell"]
    spell: SpellReferenceSchema
    via: str = Field(default="Spellcasting", min_length=1)
    via_section: StatBlockSection = "spellcasting"
    cast_level: PositiveInt | None = None


MultiattackInvocationSchema = Annotated[
    StatBlockActionInvocationSchema | CastSpellInvocationSchema,
    Field(discriminator="type"),
]


class InvokeStepSchema(MultiattackSchemaModel):
    """Validate authored invoke step data."""

    type: Literal["invoke"]
    invocation: MultiattackInvocationSchema
    times: RepeatCountSchema = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


class ChoiceStepSchema(MultiattackSchemaModel):
    """Validate authored choice step data."""

    type: Literal["choose"]
    options: list[MultiattackInvocationSchema] = Field(min_length=2)
    times: RepeatCountSchema = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


MultiattackStepSchema = Annotated[
    InvokeStepSchema | ChoiceStepSchema,
    Field(discriminator="type"),
]


class AnyAttackReplacementTargetSchema(MultiattackSchemaModel):
    """Validate authored any attack replacement target data."""

    type: Literal["any_attack"]


class ActionReplacementTargetSchema(MultiattackSchemaModel):
    """Validate authored action replacement target data."""

    type: Literal["action"]
    name: str = Field(min_length=1)
    section: StatBlockSection = "action"


class StepReplacementTargetSchema(MultiattackSchemaModel):
    """Validate authored step replacement target data."""

    type: Literal["step"]
    index: int = Field(ge=0)


ReplacementTargetSchema = Annotated[
    AnyAttackReplacementTargetSchema
    | ActionReplacementTargetSchema
    | StepReplacementTargetSchema,
    Field(discriminator="type"),
]


class MultiattackReplacementSchema(MultiattackSchemaModel):
    """Validate authored multiattack replacement data."""

    target: ReplacementTargetSchema
    replace_count: PositiveInt = 1
    maximum_uses: PositiveInt | Literal["unbounded"] = 1
    options: list[MultiattackInvocationSchema] = Field(min_length=1)
    requirement: ActionUsedThisTurnRequirementSchema | None = None


class MultiattackPlanSchema(MultiattackSchemaModel):
    """Validate authored multiattack plan data."""

    steps: list[MultiattackStepSchema] = Field(min_length=1)
    ordering: Literal["any", "strict"] = "any"
    requirement: ActionUsedThisTurnRequirementSchema | None = None
    replacements: list[MultiattackReplacementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_replacement_step_indexes(self) -> MultiattackPlanSchema:
        for replacement in self.replacements:
            target = replacement.target
            if isinstance(target, StepReplacementTargetSchema) and target.index >= len(
                self.steps
            ):
                raise ValueError(
                    f"Replacement references step {target.index}, but this "
                    f"plan has {len(self.steps)} steps."
                )
        return self


class MultiattackCapabilitySchema(MultiattackSchemaModel):
    """Validate authored multiattack capability data."""

    type: Literal["multiattack"] = "multiattack"
    plans: list[MultiattackPlanSchema] = Field(min_length=1)


def iter_stat_block_references(
    capability: MultiattackCapabilitySchema,
) -> Iterator[tuple[StatBlockSection, str]]:
    """Iterate over stat block references."""

    for plan in capability.plans:
        for step in plan.steps:
            invocations = (
                [step.invocation]
                if isinstance(step, InvokeStepSchema)
                else step.options
            )
            for invocation in invocations:
                yield from _invocation_references(invocation)
        for replacement in plan.replacements:
            if isinstance(replacement.target, ActionReplacementTargetSchema):
                yield replacement.target.section, replacement.target.name
            for invocation in replacement.options:
                yield from _invocation_references(invocation)


def _invocation_references(
    invocation: MultiattackInvocationSchema,
) -> Iterator[tuple[StatBlockSection, str]]:
    if isinstance(invocation, StatBlockActionInvocationSchema):
        yield invocation.section, invocation.name
    else:
        yield invocation.via_section, invocation.via


def build_multiattack(
    capability: MultiattackCapabilitySchema | None,
) -> Multiattack | None:
    """Build multiattack."""

    if capability is None:
        return None
    return Multiattack(
        plans=tuple(
            MultiattackPlan(
                steps=tuple(
                    MultiattackStep(
                        options=tuple(
                            _build_invocation(invocation)
                            for invocation in (
                                step.options
                                if isinstance(step, ChoiceStepSchema)
                                else (step.invocation,)
                            )
                        ),
                        times=_build_count(step.times),
                        availability=step.availability,
                    )
                    for step in plan.steps
                ),
                ordering=plan.ordering,
                replacements=tuple(
                    MultiattackReplacement(
                        target_kind=replacement.target.type,
                        target_name=getattr(replacement.target, "name", None),
                        target_step=getattr(replacement.target, "index", None),
                        options=tuple(
                            _build_invocation(option) for option in replacement.options
                        ),
                        replace_count=replacement.replace_count,
                        maximum_uses=replacement.maximum_uses,
                        requirement=_build_requirement(replacement.requirement),
                    )
                    for replacement in plan.replacements
                ),
                requirement=_build_requirement(plan.requirement),
            )
            for plan in capability.plans
        )
    )


def _build_count(
    count: int | CreatureStatCountSchema | HalfSpellLevelCountSchema,
) -> int | MultiattackCount:
    if isinstance(count, int):
        return count
    if isinstance(count, CreatureStatCountSchema):
        return MultiattackCount(kind="creature_stat", stat=count.stat)
    return MultiattackCount(kind="half_spell_level", rounding=count.round)


def _build_requirement(
    requirement: ActionUsedThisTurnRequirementSchema | None,
) -> MultiattackRequirement | None:
    if requirement is None:
        return None
    return MultiattackRequirement(
        kind="action_used_this_turn",
        action=requirement.action,
    )


def _build_invocation(
    invocation: MultiattackInvocationSchema,
) -> MultiattackInvocation:
    if isinstance(invocation, StatBlockActionInvocationSchema):
        return MultiattackInvocation(
            kind="stat_block_action",
            name=invocation.name,
            section=invocation.section,
        )
    assert isinstance(invocation, CastSpellInvocationSchema)
    return MultiattackInvocation(
        kind="cast_spell",
        name=invocation.spell.name,
        section=invocation.via_section,
        source=invocation.spell.source,
        cast_level=invocation.cast_level,
    )
