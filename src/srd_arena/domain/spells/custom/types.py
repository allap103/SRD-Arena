"""Contracts shared by registered spell resolvers."""

from collections.abc import Callable

from ...effects.results import ActionResolutionResult
from ..resolution_steps.context import SpellActionContext

DeclarativeSpellResolver = Callable[
    [SpellActionContext],
    ActionResolutionResult,
]
CustomSpellResolver = Callable[
    [SpellActionContext, DeclarativeSpellResolver],
    ActionResolutionResult,
]
