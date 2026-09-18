"""Detached gameplay facts and history, before a player's information policy."""

from dataclasses import dataclass

from .commands import GameEvent
from .observability import Observability
from .observation_models import (
    ActionObservation,
    CreatureObservation,
    GameObservation,
    TargetingObservation,
)
from .player_observation_models import AppearanceObservation, PlayerDecisionContext
from .spell_capability_observations import SpellCapabilityObservation


@dataclass(frozen=True)
class GameplayEventObservation(GameEvent):
    """Retain an unrestricted event with its immutable emission-time perception.

    History retains every recorded event for the episode. Public histories are
    derived from these records and receive independent sequence numbers.
    """

    visible_by_team: tuple[tuple[str, frozenset[str]], ...] = ()


@dataclass(frozen=True)
class GameplayConditionObservation:
    """Describe an effective condition and the occurrences supporting it."""

    name: str
    provider_ids: tuple[str, ...]
    observability: Observability


@dataclass(frozen=True)
class GameplayEffectObservation:
    """Retain the identity and disclosure classification of a creature effect."""

    instance_id: str
    definition_id: str
    label: str
    observability: Observability


@dataclass(frozen=True)
class GameplayCreatureObservation:
    """Unrestricted creature facts used by privileged and player projections."""

    combat: CreatureObservation
    appearance: AppearanceObservation
    actions_remaining: int
    bonus_action_available: bool
    concentrating_on: tuple[str, ...]
    spell_capabilities: tuple[SpellCapabilityObservation, ...]
    conditions: tuple[GameplayConditionObservation, ...]
    effects: tuple[GameplayEffectObservation, ...]
    spell_slot_spent_this_turn: bool = False


@dataclass(frozen=True)
class GameplayTeamObservation:
    """Capture perception and rule-dependent decision evidence for one team.

    Movement eligibility must be queried in the domain while capturing the
    snapshot. The later player projection needs no access to live rules/state.
    These annotations do not replace the unrestricted action offers in game.
    """

    team_id: str
    visible_creature_refs: frozenset[str]
    movement_actions: tuple[ActionObservation, ...]
    targeting: TargetingObservation | None
    decision_context: PlayerDecisionContext | None


@dataclass(frozen=True)
class GameplayObservation:
    """Shared unrestricted snapshot: current gameplay facts plus episode history.

    This is not a runtime checkpoint: RNG and executable continuations stay in
    the domain. Additional gameplay descriptors can extend this draft contract
    without creating independent state-reading paths in player projections.
    """

    schema_id: str
    episode_id: tuple[int, int]
    game: GameObservation
    creatures: tuple[GameplayCreatureObservation, ...]
    teams: tuple[GameplayTeamObservation, ...]
    history: tuple[GameplayEventObservation, ...]
    initiative_order: tuple[str, ...]
    active_turn_ref: str | None
    sunlight: bool
    terrain_movement_modes: tuple[tuple[int, int, str], ...]
