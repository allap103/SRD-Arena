"""Build domain requirements from authored requirement schemas."""

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import requirements
from .errors import CapabilityBuildError
from .supported import EXECUTABLE_REQUIREMENT_TYPES


def build_requirement(
    value: requirements.CapabilityRequirementSchema,
) -> domain.CapabilityRequirement:
    if isinstance(value, requirements.SizeRequirementSchema):
        return domain.SizeRequirement(value.maximum, value.minimum)
    if isinstance(value, requirements.ConditionRequirementSchema):
        return domain.ConditionRequirement(
            tuple(value.conditions),
            value.match,
            value.applied_by,
        )
    if isinstance(value, requirements.CreatureTypeRequirementSchema):
        return domain.CreatureTypeRequirement(tuple(value.creature_types))
    if isinstance(value, requirements.NotAffectedRequirementSchema):
        return domain.NotAffectedRequirement(value.action)
    if isinstance(value, requirements.CreatureTraitRequirementSchema):
        return domain.CreatureTraitRequirement(value.trait)
    if isinstance(value, requirements.ConditionImmunityRequirementSchema):
        return domain.ConditionImmunityRequirement(value.condition)
    if isinstance(value, requirements.RelationshipRequirementSchema):
        return domain.RelationshipRequirement(
            value.relationship,
            value.established_by,
        )
    if isinstance(value, requirements.AttackSourceRequirementSchema):
        return domain.AttackSourceRequirement(value.source, value.mode)
    if isinstance(value, requirements.WillingRequirementSchema):
        return domain.WillingRequirement()
    if isinstance(value, requirements.FreeHandRequirementSchema):
        return domain.FreeHandRequirement()
    if isinstance(value, requirements.SpellComponentRequirementSchema):
        return domain.SpellComponentRequirement(value.component)
    if isinstance(value, requirements.PerceptionRequirementSchema):
        return domain.PerceptionRequirement(value.sense, value.subject)
    if isinstance(value, requirements.HitPointRequirementSchema):
        return domain.HitPointRequirement(value.comparison, value.value)
    if isinstance(value, requirements.AnyRequirementSchema):
        return domain.AnyRequirement(
            tuple(build_requirement(item) for item in value.requirements)
        )
    return domain.AllRequirement(
        tuple(build_requirement(item) for item in value.requirements)
    )


def build_checked_requirement(
    value: object,
    content: str,
    location: str,
) -> domain.CapabilityRequirement:
    if not isinstance(value, EXECUTABLE_REQUIREMENT_TYPES):
        raise CapabilityBuildError(
            content=content,
            location=location,
            mechanic=type(value).__name__,
        )
    if isinstance(
        value,
        (requirements.AnyRequirementSchema, requirements.AllRequirementSchema),
    ):
        for index, item in enumerate(value.requirements):
            build_checked_requirement(
                item,
                content=content,
                location=f"{location}.requirements[{index}]",
            )
    return build_requirement(value)
