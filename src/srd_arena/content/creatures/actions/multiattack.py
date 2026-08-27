"""Validate and translate composed Multiattack plans from creature content."""

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
    """Reject unknown fields throughout the authored Multiattack grammar."""

    model_config = ConfigDict(extra="forbid")


class CreatureStatCountSchema(MultiattackSchemaModel):
    """Encode the ``creature_stat`` Multiattack variant with stat."""

    type: Literal["creature_stat"]
    stat: str = Field(min_length=1)


class HalfSpellLevelCountSchema(MultiattackSchemaModel):
    """Encode the ``half_spell_level`` Multiattack variant with round."""

    type: Literal["half_spell_level"]
    round: Literal["down", "up"] = "down"


DynamicCountSchema = Annotated[
    CreatureStatCountSchema | HalfSpellLevelCountSchema,
    Field(discriminator="type"),
]
RepeatCountSchema = PositiveInt | DynamicCountSchema


class ActionUsedThisTurnRequirementSchema(MultiattackSchemaModel):
    """Encode the ``action_used_this_turn`` Multiattack variant with action."""

    type: Literal["action_used_this_turn"]
    action: str = Field(min_length=1)


class SpellReferenceSchema(MultiattackSchemaModel):
    """Define the authored Multiattack fields with name and source."""

    name: str = Field(min_length=1)
    source: str | None = None


class StatBlockActionInvocationSchema(MultiattackSchemaModel):
    """Encode the ``stat_block_action`` Multiattack variant with name and section."""

    type: Literal["stat_block_action"]
    name: str = Field(min_length=1)
    section: StatBlockSection = "action"


class CastSpellInvocationSchema(MultiattackSchemaModel):
    """Encode the ``cast_spell`` Multiattack variant with spell and via."""

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
    """Encode the ``invoke`` Multiattack variant with invocation and times."""

    type: Literal["invoke"]
    invocation: MultiattackInvocationSchema
    times: RepeatCountSchema = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


class ChoiceStepSchema(MultiattackSchemaModel):
    """Encode the ``choose`` Multiattack variant with options and times."""

    type: Literal["choose"]
    options: list[MultiattackInvocationSchema] = Field(min_length=2)
    times: RepeatCountSchema = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


MultiattackStepSchema = Annotated[
    InvokeStepSchema | ChoiceStepSchema,
    Field(discriminator="type"),
]


class AnyAttackReplacementTargetSchema(MultiattackSchemaModel):
    """Encode the ``any_attack`` Multiattack variant."""

    type: Literal["any_attack"]


class ActionReplacementTargetSchema(MultiattackSchemaModel):
    """Encode the ``action`` Multiattack variant with name and section."""

    type: Literal["action"]
    name: str = Field(min_length=1)
    section: StatBlockSection = "action"


class StepReplacementTargetSchema(MultiattackSchemaModel):
    """Encode the ``step`` Multiattack variant with index."""

    type: Literal["step"]
    index: int = Field(ge=0)


ReplacementTargetSchema = Annotated[
    AnyAttackReplacementTargetSchema
    | ActionReplacementTargetSchema
    | StepReplacementTargetSchema,
    Field(discriminator="type"),
]


class MultiattackReplacementSchema(MultiattackSchemaModel):
    """Define the authored Multiattack fields with target and replace count."""

    target: ReplacementTargetSchema
    replace_count: PositiveInt = 1
    maximum_uses: PositiveInt | Literal["unbounded"] = 1
    options: list[MultiattackInvocationSchema] = Field(min_length=1)
    requirement: ActionUsedThisTurnRequirementSchema | None = None


class MultiattackPlanSchema(MultiattackSchemaModel):
    """Define the authored Multiattack fields with steps and ordering."""

    steps: list[MultiattackStepSchema] = Field(min_length=1)
    ordering: Literal["any", "strict"] = "any"
    requirement: ActionUsedThisTurnRequirementSchema | None = None
    replacements: list[MultiattackReplacementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_replacement_step_indexes(self) -> MultiattackPlanSchema:
        """Reject replacement targets outside the plan's step list.

        >>> from pydantic import ValidationError
        >>> step = {"type": "invoke", "invocation": {"type": "stat_block_action", "name": "Bite"}}
        >>> replacement = {"target": {"type": "step", "index": 1},
        ...     "options": [{"type": "stat_block_action", "name": "Claw"}]}
        >>> try:
        ...     MultiattackPlanSchema(steps=[step], replacements=[replacement])
        ... except ValidationError as error:
        ...     "references step 1" in str(error)
        True
        """
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
    """Encode the ``multiattack`` Multiattack variant with plans."""

    type: Literal["multiattack"] = "multiattack"
    plans: list[MultiattackPlanSchema] = Field(min_length=1)


def iter_stat_block_references(
    capability: MultiattackCapabilitySchema,
) -> Iterator[tuple[StatBlockSection, str]]:
    """Yield every stat-block entry a Multiattack plan can invoke.

    >>> capability = MultiattackCapabilitySchema(plans=[{"steps": [{
    ...     "type": "invoke", "invocation": {
    ...         "type": "stat_block_action", "name": "Claw"}}]}])
    >>> list(iter_stat_block_references(capability))
    [('action', 'Claw')]
    """

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
    """Translate an authored Multiattack capability into its domain plan.

    >>> capability = MultiattackCapabilitySchema(plans=[{"steps": [{
    ...     "type": "invoke", "invocation": {
    ...         "type": "stat_block_action", "name": "Claw"}, "times": 2}]}])
    >>> multiattack = build_multiattack(capability)
    >>> (multiattack.plans[0].steps[0].times,
    ...  multiattack.plans[0].steps[0].options[0].name)
    (2, 'Claw')
    >>> build_multiattack(None) is None
    True
    """

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
