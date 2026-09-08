"""Maintain team-shared facts learned while an encounter is observed."""

from dataclasses import dataclass, field

from srd_arena.domain.creatures import ObservableAppearance
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent

from .observation_models import PositionObservation
from .player_events import public_damage_from_event
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


@dataclass
class TeamKnowledge:
    """Own one allied team's shared encounter knowledge."""

    team_id: str
    creatures: dict[str, KnownCreatureFacts] = field(default_factory=dict)
    visible_in_previous_projection: set[str] = field(default_factory=set)

    def facts_for(self, creature_ref: str) -> KnownCreatureFacts:
        """Return existing facts or create an empty stable knowledge record."""

        return self.creatures.setdefault(creature_ref, KnownCreatureFacts())

    def record_events(self, events: tuple[CombatEvent, ...]) -> None:
        """Remember damage events whose targets were visible to this team."""

        for event in events:
            for damage in public_damage_from_event(event):
                if damage.target_ref in self.visible_in_previous_projection:
                    self.facts_for(
                        damage.target_ref
                    ).observed_damage_total += damage.amount

    def finish_projection(self, visible_creature_refs: set[str]) -> None:
        """Record which opponents remained visible for the next damage delta."""

        self.visible_in_previous_projection = set(visible_creature_refs)
