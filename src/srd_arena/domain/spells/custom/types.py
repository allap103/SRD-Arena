"""Contracts shared by registered spell resolvers."""

from collections.abc import Callable

from ...creatures.feature_rules.types import CapabilityActionResult
from ..resolution_steps.context import SpellActionContext

DeclarativeSpellResolver = Callable[
    [SpellActionContext],
    CapabilityActionResult,
]
CustomSpellResolver = Callable[
    [SpellActionContext, DeclarativeSpellResolver],
    CapabilityActionResult,
]
