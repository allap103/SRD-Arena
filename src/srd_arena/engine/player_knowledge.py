"""Maintain team-shared facts learned while an encounter is observed."""

from dataclasses import dataclass, field

from srd_arena.domain.creatures import ObservableAppearance
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent

from .observation_models import PositionObservation
from .player_events import public_damage_from_event, public_events_from_event
from .player_observation_models import HealthBand, PublicCombatEventObservation

_RECENT_EVENT_LIMIT = 8
_CAPABILITY_SOURCE_PREFIXES = frozenset(
    {"attack", "feature", "item", "spell", "stat_block"}
)


@dataclass
class KnownCreatureFacts:
    """Retain public facts after a creature leaves the team's current view."""

    last_known_position: PositionObservation | None = None
    appearance: ObservableAppearance | None = None
    size: str | None = None
    conditions: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    observed_capability_ids: tuple[str, ...] = ()
    health_band: HealthBand = HealthBand.UNKNOWN
    observed_damage_total: int = 0


@dataclass
class TeamKnowledge:
    """Own one allied team's shared encounter knowledge."""

    team_id: str
    creatures: dict[str, KnownCreatureFacts] = field(default_factory=dict)
    visible_in_previous_projection: set[str] = field(default_factory=set)
    recent_events: list[PublicCombatEventObservation] = field(default_factory=list)

    def facts_for(self, creature_ref: str) -> KnownCreatureFacts:
        """Return existing facts or create an empty stable knowledge record."""

        return self.creatures.setdefault(creature_ref, KnownCreatureFacts())

    def record_events(self, events: tuple[CombatEvent, ...]) -> None:
        """Remember conservative public events and facts demonstrated by them."""

        for event in events:
            public_events = public_events_from_event(
                event,
                visible_creature_refs=frozenset(self.visible_in_previous_projection),
            )
            self.recent_events.extend(public_events)
            if len(self.recent_events) > _RECENT_EVENT_LIMIT:
                del self.recent_events[:-_RECENT_EVENT_LIMIT]
            for public_event in public_events:
                if (
                    public_event.actor_ref is not None
                    and public_event.source_id is not None
                    and public_event.source_id.partition(":")[0]
                    in _CAPABILITY_SOURCE_PREFIXES
                ):
                    facts = self.facts_for(public_event.actor_ref)
                    facts.observed_capability_ids = tuple(
                        dict.fromkeys(
                            (
                                *facts.observed_capability_ids,
                                public_event.source_id,
                            )
                        )
                    )
            for damage in public_damage_from_event(event):
                if damage.target_ref in self.visible_in_previous_projection:
                    self.facts_for(
                        damage.target_ref
                    ).observed_damage_total += damage.amount

    def finish_projection(self, visible_creature_refs: set[str]) -> None:
        """Record which creatures are visible for subsequent public events."""

        self.visible_in_previous_projection = set(visible_creature_refs)
