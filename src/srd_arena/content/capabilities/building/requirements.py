"""Build domain requirements from authored requirement schemas."""

from typing import cast

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import requirements
from .errors import CapabilityBuildError
from .supported import EXECUTABLE_REQUIREMENT_TYPES


def build_requirement(
    value: requirements.ActionRequirementSchema,
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
    relationship = cast(requirements.RelationshipRequirementSchema, value)
    return domain.RelationshipRequirement(
        relationship.relationship,
        relationship.established_by,
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
    return build_requirement(value)
