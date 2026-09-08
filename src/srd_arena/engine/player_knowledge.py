"""Maintain team-shared facts learned while an encounter is observed."""

from dataclasses import dataclass, field

from srd_arena.domain.creatures import ObservableAppearance

from .observation_models import PositionObservation
from .player_observation_models import HealthBand


@dataclass
class KnownCreatureFacts:
    """Retain public facts after a creature leaves the team's current view."""

    last_known_position: PositionObservation | None = None
    appearance: ObservableAppearance | None = None
    size: str | None = None
    conditions: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    health_band: HealthBand = HealthBand.UNKNOWN
    observed_damage_total: int = 0
    last_visible_health: int | None = None


@dataclass
class TeamKnowledge:
    """Own one allied team's shared encounter knowledge."""

    team_id: str
    creatures: dict[str, KnownCreatureFacts] = field(default_factory=dict)
    visible_in_previous_projection: set[str] = field(default_factory=set)

    def facts_for(self, creature_ref: str) -> KnownCreatureFacts:
        """Return existing facts or create an empty stable knowledge record."""

        return self.creatures.setdefault(creature_ref, KnownCreatureFacts())

    def remember_visible_health(self, creature_ref: str, current_health: int) -> None:
        """Accumulate damage across consecutive visible snapshots."""

        facts = self.facts_for(creature_ref)
        if (
            creature_ref in self.visible_in_previous_projection
            and facts.last_visible_health is not None
            and current_health < facts.last_visible_health
        ):
            facts.observed_damage_total += facts.last_visible_health - current_health
        facts.last_visible_health = current_health

    def finish_projection(self, visible_creature_refs: set[str]) -> None:
        """Record which opponents remained visible for the next damage delta."""

        self.visible_in_previous_projection = set(visible_creature_refs)
