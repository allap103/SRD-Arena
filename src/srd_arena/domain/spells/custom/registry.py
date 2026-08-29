"""Closed dispatch for spell-specific Python resolution."""

from __future__ import annotations

from collections.abc import Callable

from srd_arena.domain.effects.results import ActionResolutionResult

from ..resolution_steps.context import SpellActionContext
from .slow import resolve_slow

CUSTOM_SPELL_RESOLVERS = {
    "slow": resolve_slow,
}


def resolve_custom_spell(
    context: SpellActionContext,
    resolve_declarative: Callable[[SpellActionContext], ActionResolutionResult],
) -> ActionResolutionResult:
    """Resolve one spell through its validated registered Python handler.

    Spells without an escape-hatch resolver remain fully declarative.

    >>> from types import SimpleNamespace
    >>> context = SimpleNamespace(
    ...     spell=SimpleNamespace(resolver_id=None)
    ... )
    >>> resolve_custom_spell(context, lambda current: "declarative")
    'declarative'
    """

    resolver_id = context.spell.resolver_id
    if resolver_id is None:
        return resolve_declarative(context)
    try:
        resolver = CUSTOM_SPELL_RESOLVERS[resolver_id]
    except KeyError as error:
        raise ValueError(f"Unknown custom spell resolver: {resolver_id!r}.") from error
    return resolver(context, resolve_declarative)
