"""Closed dispatch for spell-specific Python resolution."""

from __future__ import annotations

from ...creatures.feature_rules.types import CapabilityActionResult
from ..resolution_steps.context import SpellActionContext
from .slow import resolve_slow
from .types import CustomSpellResolver, DeclarativeSpellResolver

CUSTOM_SPELL_RESOLVERS: dict[str, CustomSpellResolver] = {
    "slow": resolve_slow,
}


def resolve_custom_spell(
    context: SpellActionContext,
    resolve_declarative: DeclarativeSpellResolver,
) -> CapabilityActionResult:
    """Resolve one spell through its validated registered Python handler."""

    resolver_id = context.spell.resolver_id
    if resolver_id is None:
        return resolve_declarative(context)
    try:
        resolver = CUSTOM_SPELL_RESOLVERS[resolver_id]
    except KeyError as error:
        raise ValueError(f"Unknown custom spell resolver: {resolver_id!r}.") from error
    return resolver(context, resolve_declarative)
