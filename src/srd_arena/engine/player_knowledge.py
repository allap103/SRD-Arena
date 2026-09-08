"""Maintain team-shared facts learned while an encounter is observed."""

from dataclasses import dataclass, field

from srd_arena.domain.creatures import ObservableAppearance
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent

from .observation_models import PositionObservation
from .player_events import public_damage_from_event, public_events_from_event
from .player_manifestations import manifested_state
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
    manifested_conditions: dict[str, str] = field(default_factory=dict)
    manifested_effects: dict[str, str] = field(default_factory=dict)
    observed_capability_ids: tuple[str, ...] = ()
    health_band: HealthBand = HealthBand.UNKNOWN
    observed_damage_total: int = 0


@dataclass
class TeamKnowledge:
    """Own one allied team's shared encounter knowledge."""

    team_id: str
    creatures: dict[str, KnownCreatureFacts] = field(default_factory=dict)
    recent_events: list[PublicCombatEventObservation] = field(default_factory=list)
    _next_event_sequence: int = field(default=1, init=False, repr=False)

    def facts_for(self, creature_ref: str) -> KnownCreatureFacts:
        """Return existing facts or create an empty stable knowledge record."""

        return self.creatures.setdefault(creature_ref, KnownCreatureFacts())

    def record_events(
        self,
        events: tuple[CombatEvent, ...],
        *,
        fallback_visibility: frozenset[str] = frozenset(),
    ) -> None:
        """Remember conservative public events and facts demonstrated by them."""

        for event in events:
            visible = (
                dict(event.visible_by_team).get(self.team_id, frozenset())
                if event.visible_by_team is not None
                else fallback_visibility
            )
            evidence = manifested_state(event)
            if evidence is not None and event.creature_ref in visible:
                assert event.creature_ref is not None
                facts = self.facts_for(event.creature_ref)
                instances = (
                    facts.manifested_conditions
                    if evidence.is_condition
                    else facts.manifested_effects
                )
                instances[evidence.instance_id] = evidence.name
            public_events = public_events_from_event(
                event,
                visible_creature_refs=visible,
                first_sequence=self._next_event_sequence,
            )
            self._next_event_sequence += len(public_events)
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
                if damage.target_ref in visible:
                    self.facts_for(
                        damage.target_ref
                    ).observed_damage_total += damage.amount
