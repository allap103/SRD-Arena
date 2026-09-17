"""Project detached gameplay facts through the supported information policy."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Literal, cast

from .area_observation_models import AreaTemplateObservation
from .gameplay_observation_models import (
    GameplayCreatureObservation,
    GameplayObservation,
)
from .observation_models import (
    ActionObservation,
    DecisionObservation,
    EncounterCompletionObservation,
    GridObservation,
    PositionObservation,
    TargetingObservation,
    TerrainCellObservation,
)
from .observation_policy import Group, HealthIntervals, ObservationPolicy
from .player_action_observations import player_action_observations
from .player_events import public_damage_from_event, public_events_from_event
from .player_observation_models import (
    AppearanceObservation,
    PlayerDecisionContext,
    PublicCombatEventObservation,
    PublicEventKind,
)
from .spell_capability_observations import SpellCapabilityObservation
from .spell_cast_observation_models import SpellCastOptions

FILTERED_OBSERVATION_SCHEMA_ID = "filtered-observation-v5"


@dataclass(frozen=True)
class HealthInterval:
    """A fractional health interval with explicit endpoint inclusion."""

    lower: float
    upper: float
    lower_inclusive: bool
    upper_inclusive: bool


def health_interval(
    health: int, maximum: int, intervals: HealthIntervals
) -> HealthInterval:
    """Compute relative intervals without retaining exact HP in their output."""
    if maximum <= 0:
        raise ValueError("Effective maximum health must be positive")
    ratio = max(0.0, min(1.0, health / maximum))
    if ratio == 0 or (ratio == 1 and intervals.distinguish_full_health):
        return HealthInterval(ratio, ratio, True, True)
    for lower, upper in zip(
        intervals.boundaries, intervals.boundaries[1:], strict=False
    ):
        if ratio <= upper:
            return HealthInterval(
                lower,
                upper,
                False,
                not (upper == 1 and intervals.distinguish_full_health),
            )
    raise AssertionError("Validated intervals must cover the health ratio")


@dataclass(frozen=True)
class FilteredHealth:
    """Exactly one disclosed representation; hidden health uses a null field."""

    current: int | None = None
    maximum: int | None = None
    interval: HealthInterval | None = None


@dataclass(frozen=True)
class FilteredCreature:
    """Supported creature facts; null differs from known zero or absence."""

    creature_ref: str
    allegiance: Group
    knowledge: Literal["current", "last_known", "unknown"]
    currently_visible: bool
    position: PositionObservation | None = None
    size: str | None = None
    appearance: AppearanceObservation | None = None
    creature_type: str | None = None
    health: FilteredHealth | None = None
    temporary_health: int | bool | None = None
    defeated: bool | None = None
    armor_class: int | None = None
    observed_damage_total: int | None = None


@dataclass(frozen=True)
class FilteredAction:
    """Mandatory command routing without optional labels, reasons or previews.

    IDs are opaque decision-local tokens. Their naming is not a descriptor
    contract; availability remains the established player-safe attempt mask.
    """

    id: str
    kind: str
    creature_ref: str
    target_ref: str | None
    source_trigger_id: str | None
    enabled: bool
    availability: str
    required_configuration: str | None
    spell: SpellCapabilityObservation | None = None
    area_template: AreaTemplateObservation | None = None
    spell_cast: SpellCastOptions | None = None


@dataclass(frozen=True)
class FilteredObservation:
    """Versioned JSON-facing contract for the initial supported policy slice."""

    schema_id: str
    perspective_creature_ref: str
    perspective_team_id: str
    encounter_id: str
    grid: GridObservation
    round_number: int | None
    active_turn_ref: str | None
    initiative_order: tuple[str, ...] | None
    creatures: tuple[FilteredCreature, ...]
    terrain: tuple[TerrainCellObservation, ...]
    sunlight: bool | None
    recent_events: tuple[PublicCombatEventObservation, ...]
    decision: DecisionObservation
    action_details: tuple[FilteredAction, ...]
    targeting: TargetingObservation | None
    decision_context: PlayerDecisionContext | None
    completion: EncounterCompletionObservation | None
    requires_automatic_advance: bool


@dataclass
class PolicyProjector:
    """Own policy-specific memory, retaining only admitted detached facts.

    Consume snapshots in episode order, including automatic steps. A changed
    episode ID clears memory. The fixed perspective never follows turn owners.
    """

    policy: ObservationPolicy
    perspective_creature_ref: str
    _episode: tuple[int, int] | None = field(default=None, init=False)
    _cursor: int = field(default=0, init=False)
    _sequence: int = field(default=1, init=False)
    _rows: dict[str, FilteredCreature] = field(default_factory=dict, init=False)
    _damage: dict[str, int] = field(default_factory=dict, init=False)
    _events: list[PublicCombatEventObservation] = field(
        default_factory=list, init=False
    )

    def __post_init__(self) -> None:
        self.policy.validate_support()

    def project(self, snapshot: GameplayObservation) -> FilteredObservation:
        """Filter a frozen snapshot without accessing the mutable game."""
        encounter = snapshot.game.encounter
        if encounter is None:
            raise ValueError("An active encounter is required")
        own = next(
            (
                c
                for c in snapshot.creatures
                if c.combat.creature_ref == self.perspective_creature_ref
            ),
            None,
        )
        if own is None:
            raise ValueError("Perspective creature is not in this encounter")
        team_id = own.combat.team_id
        team = next(t for t in snapshot.teams if t.team_id == team_id)
        groups: dict[str, Group] = {
            c.combat.creature_ref: "own"
            if c is own
            else "ally"
            if c.combat.team_id == team_id
            else "enemy"
            for c in snapshot.creatures
        }
        if snapshot.episode_id != self._episode:
            self._episode = snapshot.episode_id
            self._cursor = 0
            self._sequence = 1
            self._rows.clear()
            self._damage.clear()
            self._events.clear()
        if len(snapshot.history) < self._cursor:
            raise ValueError("Policy memory cannot consume history backwards")
        self._record_history(snapshot, team_id, groups)
        rows = []
        for creature in snapshot.creatures:
            ref = creature.combat.creature_ref
            group = groups[ref]
            visible = ref in team.visible_creature_refs
            if group != "enemy" or visible:
                row = self._current_row(creature, group, visible)
                self._rows[ref] = row
            elif (
                self.policy.memory.for_group(group) == "last_known"
                and ref in self._rows
            ):
                row = replace(
                    self._rows[ref], knowledge="last_known", currently_visible=False
                )
            else:
                self._rows.pop(ref, None)
                row = FilteredCreature(ref, group, "unknown", False)
            rows.append(
                replace(
                    row,
                    observed_damage_total=(
                        self._damage.get(ref, 0)
                        if self.policy.history.accumulated.damage_received.for_group(
                            group
                        )
                        == "exact"
                        and (row.knowledge != "unknown" or ref in self._damage)
                        else None
                    ),
                )
            )
        actions = player_action_observations(
            tuple(a for a in team.movement_actions if not a.kind.startswith("system_")),
            visible_creature_refs=team.visible_creature_refs,
            allied_creature_refs=frozenset(
                ref for ref, group in groups.items() if group != "enemy"
            ),
        )
        return FilteredObservation(
            FILTERED_OBSERVATION_SCHEMA_ID,
            self.perspective_creature_ref,
            team_id,
            encounter.encounter_id,
            encounter.grid,
            encounter.round_number
            if self.policy.encounter.round == "include"
            else None,
            snapshot.active_turn_ref
            if self.policy.encounter.active_turn == "include"
            else None,
            snapshot.initiative_order
            if self.policy.encounter.initiative == "order"
            else None,
            tuple(rows),
            encounter.terrain,
            snapshot.sunlight if self.policy.battlefield.environment == "all" else None,
            tuple(self._events),
            encounter.decision,
            tuple(
                FilteredAction(
                    a.id,
                    a.kind,
                    a.creature_ref,
                    a.target_ref,
                    a.source_trigger_id,
                    a.enabled,
                    a.availability,
                    a.required_configuration,
                    (descriptor := self._spell_descriptor(snapshot, a, groups)),
                    self._area_template(a, descriptor),
                    a.spell_cast,
                )
                for a in actions
            ),
            team.targeting,
            team.decision_context
            if self.policy.decisions.context == "permitted"
            else None,
            snapshot.game.completion,
            snapshot.game.requires_automatic_advance,
        )

    def _area_template(
        self, action: ActionObservation, descriptor: SpellCapabilityObservation | None
    ) -> AreaTemplateObservation | None:
        """Expose geometry from permitted allied spell previews, without occupants."""
        if descriptor is None:
            return None
        preview = action.area_preview
        if preview is None:
            return None
        geometry = preview.get("continuous_area")
        if not isinstance(geometry, Mapping):
            return None
        shape = geometry.get("shape")
        if not isinstance(shape, str) or shape not in (
            "cone",
            "line",
            "cube",
            "radius",
        ):
            return None
        directional = geometry.get("direction") is not None
        if (directional and shape == "radius") or (
            not directional and shape not in ("cube", "radius")
        ):
            return None
        size = geometry.get("radius" if shape == "radius" else "length")
        threshold = geometry.get("coverage_threshold")
        width = geometry.get("width")
        if not isinstance(size, (int, float)) or size <= 0:
            return None
        if directional and not isinstance(threshold, (int, float)):
            return None
        if shape == "line" and not isinstance(width, (int, float)):
            return None
        return AreaTemplateObservation(
            cast(Literal["cone", "line", "cube", "radius"], shape),
            "directional" if directional else "point",
            int(size),
            float(width) if isinstance(width, (int, float)) else None,
            float(threshold) if isinstance(threshold, (int, float)) else None,
        )

    def _spell_descriptor(
        self,
        snapshot: GameplayObservation,
        action: ActionObservation,
        groups: dict[str, Group],
    ) -> SpellCapabilityObservation | None:
        """Join public action metadata to an allied catalog, never an enemy sheet."""
        if (
            self.policy.decisions.capability_descriptions != "permitted"
            or groups.get(action.creature_ref) not in ("own", "ally")
            or action.source_id is None
        ):
            return None
        creature = next(
            c
            for c in snapshot.creatures
            if c.combat.creature_ref == action.creature_ref
        )
        matches = tuple(
            s
            for s in creature.spell_capabilities
            if s.spell_id == action.source_id
            and s.grant_id == action.grant_id
            and s.cast_level
            == (
                action.resource_level
                if action.resource_level is not None
                else s.spell_level
            )
        )
        return matches[0] if len(matches) == 1 else None

    def _current_row(
        self, creature: GameplayCreatureObservation, group: Group, visible: bool
    ) -> FilteredCreature:
        combat = creature.combat
        policy = self.policy.creatures
        mode = policy.health.disclosure.for_group(group)
        health = (
            FilteredHealth(combat.health, combat.max_health)
            if mode == "exact"
            else FilteredHealth(
                interval=health_interval(
                    combat.health, combat.max_health, policy.health.intervals
                )
            )
            if mode == "interval"
            else None
        )
        temporary_mode = policy.temporary_health.for_group(group)
        return FilteredCreature(
            combat.creature_ref,
            group,
            "current",
            visible,
            combat.position,
            combat.size,
            creature.appearance,
            creature.appearance.apparent_creature_type,
            health,
            combat.temporary_hit_points
            if temporary_mode == "exact"
            else combat.temporary_hit_points > 0
            if temporary_mode == "presence"
            else None,
            not combat.is_alive
            if policy.defeated.for_group(group) == "include"
            else None,
            combat.armor_class
            if policy.armor_class.for_group(group) == "exact"
            else None,
        )

    def _record_history(
        self, snapshot: GameplayObservation, team_id: str, groups: dict[str, Group]
    ) -> None:
        for event in snapshot.history[self._cursor :]:
            visible = dict(event.visible_by_team).get(team_id, frozenset())
            for damage in public_damage_from_event(event):
                if (
                    damage.target_ref in visible
                    and damage.target_ref in groups
                    and (
                        self.policy.history.accumulated.damage_received.for_group(
                            groups[damage.target_ref]
                        )
                        == "exact"
                    )
                ):
                    self._damage[damage.target_ref] = (
                        self._damage.get(damage.target_ref, 0) + damage.amount
                    )
            if (
                self.policy.history.events == "hidden"
                or not self.policy.history.recent_event_limit
            ):
                continue
            for public in public_events_from_event(
                event, visible_creature_refs=visible
            ):
                # These groups are explicitly hidden in the supported slice.
                if public.kind in {PublicEventKind.CONDITION, PublicEventKind.EFFECT}:
                    continue
                if public.kind == PublicEventKind.DEFEAT and (
                    public.target_ref not in groups
                    or self.policy.creatures.defeated.for_group(
                        groups[public.target_ref]
                    )
                    == "omit"
                ):
                    continue
                self._events.append(replace(public, seq=self._sequence, source_id=None))
                self._sequence += 1
            del self._events[: -self.policy.history.recent_event_limit]
        self._cursor = len(snapshot.history)
