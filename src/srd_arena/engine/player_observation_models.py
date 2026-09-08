"""Immutable semantic observations exposed to non-privileged game controllers."""

from dataclasses import dataclass
from enum import StrEnum

from .observation_models import (
    ActionObservation,
    DecisionObservation,
    EncounterCompletionObservation,
    GridObservation,
    PositionObservation,
    ResourcePoolObservation,
    SpellSlotObservation,
    TargetingObservation,
    TerrainCellObservation,
)
from .spell_capability_observations import SpellCapabilityObservation

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


class PublicEventKind(StrEnum):
    """Classify the small set of occurrences exposed to player controllers."""

    ATTACK = "attack"
    CONDITION = "condition"
    EFFECT = "effect"
    DEFEAT = "defeat"
    FEATURE = "feature"
    ITEM = "item"
    MOVEMENT = "movement"
    RETALIATION = "retaliation"
    SPELL = "spell"
    STAT_BLOCK_ACTION = "stat_block_action"


@dataclass(frozen=True)
class PublicCombatEventObservation:
    """Expose a visible occurrence with a team-local, episode-local sequence.

    ``seq`` counts published records, not internal events. It stays monotonic
    when older records leave the bounded history and restarts with the episode.
    """

    seq: int
    kind: PublicEventKind
    actor_ref: str | None = None
    target_ref: str | None = None
    source_id: str | None = None
    outcome: str | None = None
    amount: int | None = None


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
    """Expose only facts available to the observing creature's allied team.

    Resource and concentration fields are exact for allies and ``None`` for
    enemies. An empty allied tuple means no slots, pools, or concentration;
    it is distinct from an opponent's unknown state.
    """

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
    observed_capability_ids: tuple[str, ...]
    health: int | None = None
    maximum_health: int | None = None
    temporary_hit_points: int | None = None
    armor_class: int | None = None
    action_available: bool | None = None
    bonus_action_available: bool | None = None
    reaction_available: bool | None = None
    movement_remaining_feet: int | None = None
    actions_remaining: int | None = None
    attacks_remaining: int | None = None
    attacks_per_attack_action: int | None = None
    spell_slots: tuple[SpellSlotObservation, ...] | None = None
    resource_pools: tuple[ResourcePoolObservation, ...] | None = None
    concentrating_on: tuple[str, ...] | None = None
    spell_capabilities: tuple[SpellCapabilityObservation, ...] | None = None


@dataclass(frozen=True)
class PlayerDecisionContext:
    """Describe an owned interrupt without disclosing private resolution data.

    Participant references are limited to currently perceived creatures. The
    enclosing decision ID addresses the response; internal occurrence IDs and
    continuation objects are deliberately omitted.
    """

    trigger: str
    can_pass: bool
    actor_ref: str | None = None
    target_ref: str | None = None
    roll_kind: str | None = None
    offered_roll_mode: str | None = None


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
    recent_events: tuple[PublicCombatEventObservation, ...]
    completion: EncounterCompletionObservation | None
    requires_automatic_advance: bool
    targeting: TargetingObservation | None = None
    decision_context: PlayerDecisionContext | None = None

    def creature(self, creature_ref: str) -> PlayerCreatureObservation:
        """Return a semantic creature row by its stable encounter reference."""

        return next(
            creature
            for creature in self.creatures
            if creature.creature_ref == creature_ref
        )
