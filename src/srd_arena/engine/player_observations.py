"""Apply player knowledge to detached gameplay observations."""

from dataclasses import replace
from typing import Protocol

from .gameplay_observation_models import (
    GameplayCreatureObservation,
    GameplayObservation,
)
from .observability import Observability
from .player_action_observations import player_action_observations
from .player_knowledge import TeamKnowledge
from .player_observation_models import (
    PLAYER_OBSERVATION_SCHEMA_ID,
    CreatureAllegiance,
    HealthBand,
    KnowledgeState,
    PlayerCreatureObservation,
    PlayerObservation,
)


class GameplaySource(Protocol):
    """Supply detached gameplay observations to a player-facing adapter."""

    def observe_gameplay(self) -> GameplayObservation: ...


def observe_player_session(
    session: GameplaySource,
    perspective_team_id: str,
    knowledge: TeamKnowledge,
) -> PlayerObservation:
    """Project a session through the same source used by privileged consumers."""

    return project_player_observation(
        session.observe_gameplay(),
        perspective_team_id,
        knowledge,
    )


def project_player_observation(
    snapshot: GameplayObservation,
    perspective_team_id: str,
    knowledge: TeamKnowledge,
) -> PlayerObservation:
    """Apply team knowledge without querying or retaining mutable domain state.

    Knowledge must consume snapshots in episode order. Repeated projection of
    one history prefix is idempotent; a new episode resets accumulated facts.
    """

    encounter = snapshot.game.encounter
    if encounter is None:
        raise RuntimeError("Cannot produce a player observation without an encounter.")
    team = next(
        (team for team in snapshot.teams if team.team_id == perspective_team_id), None
    )
    if team is None:
        raise KeyError(f"Unknown perspective team '{perspective_team_id}'.")
    if knowledge.team_id != perspective_team_id:
        raise ValueError("Player knowledge belongs to a different team.")
    knowledge.record_history(snapshot.episode_id, snapshot.history)
    creatures = tuple(
        _observe_player_creature(
            creature=creature,
            allied=creature.combat.team_id == perspective_team_id,
            visible=creature.combat.creature_ref in team.visible_creature_refs,
            knowledge=knowledge,
        )
        for creature in snapshot.creatures
    )
    return PlayerObservation(
        schema_id=PLAYER_OBSERVATION_SCHEMA_ID,
        perspective_team_id=perspective_team_id,
        encounter_id=encounter.encounter_id,
        grid=encounter.grid,
        round_number=encounter.round_number,
        decision=encounter.decision,
        creatures=creatures,
        initiative_order=snapshot.initiative_order,
        action_details=player_action_observations(
            tuple(
                action
                for action in team.movement_actions
                if not action.kind.startswith("system_")
            ),
            visible_creature_refs=team.visible_creature_refs,
        ),
        terrain=encounter.terrain,
        recent_events=tuple(knowledge.recent_events),
        completion=snapshot.game.completion,
        requires_automatic_advance=snapshot.game.requires_automatic_advance,
        targeting=team.targeting,
        decision_context=team.decision_context,
    )


def _observe_player_creature(
    *,
    creature: GameplayCreatureObservation,
    allied: bool,
    visible: bool,
    knowledge: TeamKnowledge,
) -> PlayerCreatureObservation:
    combat = creature.combat
    facts = knowledge.facts_for(combat.creature_ref)
    if visible:
        facts.last_known_position = combat.position
        facts.appearance = creature.appearance
        facts.size = combat.size
        facts.health_band = _health_band(combat.health, combat.max_health)
        active_condition_ids = {
            provider
            for condition in creature.conditions
            for provider in condition.provider_ids
        }
        facts.manifested_conditions = {
            instance: name
            for instance, name in facts.manifested_conditions.items()
            if instance in active_condition_ids
        }
        active_effect_ids = {effect.instance_id for effect in creature.effects}
        facts.manifested_effects = {
            instance: name
            for instance, name in facts.manifested_effects.items()
            if instance in active_effect_ids
        }
        facts.conditions = tuple(
            dict.fromkeys(
                condition.name
                for condition in creature.conditions
                if allied
                or condition.observability is Observability.OBVIOUS
                or any(
                    provider in facts.manifested_conditions
                    for provider in condition.provider_ids
                )
            )
        )
        facts.effects = tuple(
            dict.fromkeys(
                effect.label
                for effect in creature.effects
                if allied
                or effect.observability is Observability.OBVIOUS
                or effect.instance_id in facts.manifested_effects
            )
        )
    known = facts.last_known_position is not None
    common = PlayerCreatureObservation(
        creature_ref=combat.creature_ref,
        allegiance=CreatureAllegiance.ALLY if allied else CreatureAllegiance.ENEMY,
        knowledge=(
            KnowledgeState.ALLY_SHARED
            if allied
            else KnowledgeState.VISIBLE
            if visible
            else KnowledgeState.LAST_KNOWN
            if known
            else KnowledgeState.UNKNOWN
        ),
        currently_visible=visible,
        position=facts.last_known_position,
        size=facts.size,
        appearance=facts.appearance,
        health_band=facts.health_band,
        observed_damage_total=None
        if allied or not known
        else facts.observed_damage_total,
        known_conditions=facts.conditions,
        known_effects=facts.effects,
        observed_capability_ids=() if allied else facts.observed_capability_ids,
    )
    if not allied:
        return common
    return replace(
        common,
        health=combat.health,
        maximum_health=combat.max_health,
        temporary_hit_points=combat.temporary_hit_points,
        armor_class=combat.armor_class,
        action_available=creature.actions_remaining > 0,
        bonus_action_available=creature.bonus_action_available,
        reaction_available=combat.reaction_available,
        movement_remaining_feet=combat.movement_remaining_feet,
        actions_remaining=creature.actions_remaining,
        attacks_remaining=combat.attacks_remaining,
        attacks_per_attack_action=combat.attacks_per_attack_action,
        spell_slots=combat.spell_slots,
        spell_capabilities=creature.spell_capabilities,
        resource_pools=combat.resource_pools,
        concentrating_on=creature.concentrating_on,
    )


def _health_band(health: int, maximum: int) -> HealthBand:
    if health <= 0:
        return HealthBand.DEFEATED
    if health >= maximum:
        return HealthBand.UNHURT
    if health * 2 > maximum:
        return HealthBand.WOUNDED
    if health * 4 > maximum:
        return HealthBand.BLOODIED
    return HealthBand.NEAR_DEFEAT
