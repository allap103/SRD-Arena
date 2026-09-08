"""Immutable semantic observations exposed to non-privileged game controllers."""

from dataclasses import dataclass
from enum import StrEnum

from .observation_models import (
    ActionObservation,
    DecisionObservation,
    EncounterCompletionObservation,
    GridObservation,
    PositionObservation,
    TerrainCellObservation,
)

PLAYER_OBSERVATION_SCHEMA_ID = "player-observation-v1-draft"


class HealthBand(StrEnum):
    """Describe visible enemy injury without exposing exact hit points."""

    UNKNOWN = "unknown"
    UNHURT = "unhurt"
    WOUNDED = "wounded"
    BLOODIED = "bloodied"
    NEAR_DEFEAT = "near_defeat"
    DEFEATED = "defeated"


class CreatureAllegiance(StrEnum):
    """Describe a combatant relative to the observing team."""

    ALLY = "ally"
    ENEMY = "enemy"


class KnowledgeState(StrEnum):
    """Describe the freshness of the location and facts in an entity row."""

    ALLY_SHARED = "ally_shared"
    VISIBLE = "visible"
    LAST_KNOWN = "last_known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AppearanceObservation:
    """Expose ordinary visible equipment and anatomy without private statistics."""

    armor_label: str | None
    armor_category: str
    has_shield: bool
    visible_weapons: tuple[str, ...]
    spellcasting_focus_label: str | None
    spellcasting_focus_kind: str
    obvious_features: tuple[str, ...]
    apparent_creature_type: str | None


@dataclass(frozen=True)
class PlayerCreatureObservation:
    """Expose only facts available to the observing creature's allied team."""

    creature_ref: str
    allegiance: CreatureAllegiance
    knowledge: KnowledgeState
    currently_visible: bool
    position: PositionObservation | None
    size: str | None
    appearance: AppearanceObservation | None
    health_band: HealthBand
    observed_damage_total: int | None
    known_conditions: tuple[str, ...]
    known_effects: tuple[str, ...]
    health: int | None = None
    maximum_health: int | None = None
    temporary_hit_points: int | None = None
    armor_class: int | None = None
    action_available: bool | None = None
    bonus_action_available: bool | None = None
    reaction_available: bool | None = None
    movement_remaining_feet: int | None = None


@dataclass(frozen=True)
class PlayerObservation:
    """Represent one team's framework-neutral semantic view of an encounter."""

    schema_id: str
    perspective_team_id: str
    encounter_id: str
    grid: GridObservation
    round_number: int
    decision: DecisionObservation
    creatures: tuple[PlayerCreatureObservation, ...]
    initiative_order: tuple[str, ...]
    action_details: tuple[ActionObservation, ...]
    terrain: tuple[TerrainCellObservation, ...]
    completion: EncounterCompletionObservation | None
    requires_automatic_advance: bool

    def creature(self, creature_ref: str) -> PlayerCreatureObservation:
        """Return a semantic creature row by its stable encounter reference."""

        return next(
            creature
            for creature in self.creatures
            if creature.creature_ref == creature_ref
        )
