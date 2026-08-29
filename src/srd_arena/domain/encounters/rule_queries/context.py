"""Define the narrow encounter data required by typed rule queries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from srd_arena.domain.effects.conditions import AppliedCondition
from srd_arena.domain.effects.runtime import OngoingEffect
from srd_arena.domain.rolls.randomness import DiceRoller

from ..definitions import EncounterDefinition
from ..encounter_models.actions import CreatureRef
from ..encounter_models.state import EncounterCreatureState


class EffectQueryContext(Protocol):
    """Expose active typed effects without requiring the encounter aggregate."""

    @property
    def ongoing_effects(self) -> Sequence[OngoingEffect]:
        """Return active ongoing effects and their runtime provenance."""


class CreatureEffectQueryContext(EffectQueryContext, Protocol):
    """Add the combatant lookup needed by creature-specific effect queries."""

    @property
    def creatures(self) -> Mapping[CreatureRef, EncounterCreatureState]:
        """Return encounter combatants keyed by stable creature reference."""


class ConditionRuleQueryContext(CreatureEffectQueryContext, Protocol):
    """Add sourced conditions needed by permission and speed queries."""

    @property
    def conditions(self) -> Sequence[AppliedCondition]:
        """Return sourced condition applications active in the encounter."""


class MovementRuleQueryContext(ConditionRuleQueryContext, Protocol):
    """Add authored grid configuration needed to derive movement budgets."""

    @property
    def definition(self) -> EncounterDefinition:
        """Return the authored encounter definition containing the grid."""


class DamageRuleQueryContext(CreatureEffectQueryContext, Protocol):
    """Add encounter randomness needed to resolve damage reductions."""

    @property
    def dice(self) -> DiceRoller:
        """Return the encounter-owned source of dice randomness."""
