"""Build domain spells from authored spell schemas."""

from srd_arena.content.capabilities import build_capability
from srd_arena.content.common.sources import slug
import srd_arena.domain.capabilities as capability_domain
from srd_arena.domain.spells import Spell
from .schema import SpellSchema


def build_spell(spell_schema: SpellSchema) -> Spell:
    """Build a domain spell from validated authored content."""
    definition = build_spell_definition(spell_schema)
    return Spell(
        id=slug(spell_schema.public_name),
        name=spell_schema.public_name,
        source=spell_schema.source,
        level=spell_schema.level,
        school=spell_schema.school,
        components=dict(spell_schema.components),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in spell_schema.duration
            if isinstance(duration, dict)
        ),
        definition=definition,
        activation=build_activation(spell_schema),
    )


def build_spell_definition(
    spell_schema: SpellSchema,
) -> capability_domain.CapabilityDefinition | None:
    """Build an executable spell through the shared capability builder."""
    if not spell_schema.executable:
        return None
    assert spell_schema.capability is not None
    capability = spell_schema.capability
    return build_capability(
        target=capability.target,
        resolution=capability.resolution,
        content=f"Spell '{spell_schema.public_name}'",
        condition_selection=capability.condition_application,
        duration=capability.duration,
        scaling_rules=capability.scaling,
        triggers=capability.outcome_triggers,
        reactivation_ends_previous=capability.reactivation_ends_previous,
        blocked_self_removal_conditions=capability.blocked_self_removal_conditions,
    )


def build_activation(
    spell_schema: SpellSchema,
) -> capability_domain.CapabilityActivation | None:
    if not spell_schema.time:
        return None
    activation_by_unit: dict[str, capability_domain.CapabilityActivation] = {
        "action": "action",
        "bonus": "bonus_action",
        "reaction": "reaction",
    }
    unit = spell_schema.time[0].get("unit")
    return activation_by_unit.get(unit) if isinstance(unit, str) else None
