"""Project complete engine state into a team-relative semantic observation."""

from srd_arena.domain.creatures import ObservableAppearance
from srd_arena.domain.effects.runtime import OngoingEffectKind
from srd_arena.domain.encounters import rule_queries
from srd_arena.domain.encounters.encounter import EncounterState

from .action_observations import observe_scene
from .observability import Observability, condition_observability, effect_observability
from .observation_models import (
    DecisionObservation,
    EncounterCompletionObservation,
    GridObservation,
    PositionObservation,
    TerrainCellObservation,
)
from .player_action_observations import player_action_observations
from .player_decision_observations import observe_player_decision
from .player_knowledge import TeamKnowledge
from .player_movement_observations import player_movement_observations
from .player_observation_models import (
    PLAYER_OBSERVATION_SCHEMA_ID,
    AppearanceObservation,
    CreatureAllegiance,
    HealthBand,
    KnowledgeState,
    PlayerCreatureObservation,
    PlayerObservation,
)
from .protocols import GameEngine
from .queries import SessionRead
from .resource_observations import observe_resource_pools, observe_spell_slots
from .spell_capability_observations import observe_spell_capabilities
from .targeting_observations import observe_player_targeting


def observe_player_session(
    session: GameEngine,
    perspective_team_id: str,
    knowledge: TeamKnowledge,
) -> PlayerObservation:
    """Return a non-privileged semantic observation for one allied team."""

    read = session._read()
    state = read.encounter_state
    if state is None:
        raise RuntimeError("Cannot produce a player observation without an encounter.")
    if perspective_team_id not in read.team_ids:
        raise KeyError(f"Unknown perspective team '{perspective_team_id}'.")
    if knowledge.team_id != perspective_team_id:
        raise ValueError("Player knowledge belongs to a different team.")

    decision = state.current_decision()
    allied_refs = {
        creature_ref
        for creature_ref, team_id in read.creature_team_ids.items()
        if team_id == perspective_team_id
    }
    living_viewers = tuple(
        creature_ref
        for creature_ref in allied_refs
        if state.creatures[creature_ref].is_alive
    )
    creatures: list[PlayerCreatureObservation] = []
    for creature_ref in state.creatures:
        allied = creature_ref in allied_refs
        visible = allied or any(
            rule_queries.creature_can_see_creature(
                state,
                viewer_ref,
                creature_ref,
            )
            for viewer_ref in living_viewers
        )
        creatures.append(
            _observe_player_creature(
                state=state,
                creature_ref=creature_ref,
                allied=allied,
                visible=visible,
                knowledge=knowledge,
            )
        )

    completion = _observe_completion(read)
    grid = state.definition.grid
    decision_team_id = read.creature_team_ids[decision.creature_ref]
    scene = observe_scene(read)
    visible_refs = frozenset(
        creature.creature_ref for creature in creatures if creature.currently_visible
    )
    return PlayerObservation(
        schema_id=PLAYER_OBSERVATION_SCHEMA_ID,
        perspective_team_id=perspective_team_id,
        encounter_id=state.encounter_id,
        grid=GridObservation(grid.width, grid.height),
        round_number=state.round.number,
        decision=DecisionObservation(
            id=f"{decision.id}@{read.decision_epoch}:{read.decision_revision}",
            kind=decision.kind,
            creature_ref=decision.creature_ref,
        ),
        creatures=tuple(creatures),
        initiative_order=tuple(state.initiative_order),
        action_details=(
            player_action_observations(
                player_movement_observations(
                    tuple(
                        action
                        for action in scene.action_details
                        if not action.kind.startswith("system_")
                    ),
                    state,
                    visible_refs,
                ),
                visible_creature_refs=visible_refs,
            )
            if decision_team_id == perspective_team_id
            else ()
        ),
        terrain=tuple(
            TerrainCellObservation(
                position=PositionObservation(cell.position.x, cell.position.y),
                traversal=cell.traversal.value,
                cover=cell.cover.value,
            )
            for cell in state.definition.terrain
        ),
        recent_events=tuple(knowledge.recent_events),
        completion=completion,
        requires_automatic_advance=read.requires_automatic_advance,
        targeting=observe_player_targeting(state, frozenset(allied_refs)),
        decision_context=observe_player_decision(
            decision, allied_refs=frozenset(allied_refs), visible_refs=visible_refs
        ),
    )


def _observe_player_creature(
    *,
    state: EncounterState,
    creature_ref: str,
    allied: bool,
    visible: bool,
    knowledge: TeamKnowledge,
) -> PlayerCreatureObservation:
    creature_state = state.creatures[creature_ref]
    creature = creature_state.creature
    facts = knowledge.facts_for(creature_ref)
    if visible:
        facts.last_known_position = PositionObservation(
            creature_state.position.x,
            creature_state.position.y,
        )
        facts.appearance = creature.observable_appearance
        facts.size = creature.size
        maximum_health = rule_queries.effective_maximum_health(
            state,
            creature_ref,
        ).value
        facts.health_band = _health_band(creature.get_health(), maximum_health)
        active_conditions = state.effective_conditions_for(creature_ref).conditions
        active_condition_ids = {
            provider_id
            for applied in active_conditions
            for provider_id in applied.provider_ids
        }
        facts.manifested_conditions = {
            instance_id: name
            for instance_id, name in facts.manifested_conditions.items()
            if instance_id in active_condition_ids
        }
        active_effect_ids = {
            effect.identity.id
            for effect in state.ongoing_effects
            if creature_ref in effect.target_refs
        }
        facts.manifested_effects = {
            instance_id: name
            for instance_id, name in facts.manifested_effects.items()
            if instance_id in active_effect_ids
        }
        facts.conditions = tuple(
            dict.fromkeys(
                applied.condition.value
                for applied in active_conditions
                if allied
                or condition_observability(applied.condition) is Observability.OBVIOUS
                or any(
                    provider_id in facts.manifested_conditions
                    for provider_id in applied.provider_ids
                )
            )
        )
        facts.effects = tuple(
            dict.fromkeys(
                effect.label or effect.identity.source.definition_id
                for effect in state.ongoing_effects
                if creature_ref in effect.target_refs
                and (
                    allied
                    or effect_observability(effect) is Observability.OBVIOUS
                    or effect.identity.id in facts.manifested_effects
                )
            )
        )
    if allied:
        return _observe_ally(state, creature_ref, knowledge)

    known = facts.last_known_position is not None
    return PlayerCreatureObservation(
        creature_ref=creature_ref,
        allegiance=CreatureAllegiance.ENEMY,
        knowledge=(
            KnowledgeState.VISIBLE
            if visible
            else KnowledgeState.LAST_KNOWN
            if known
            else KnowledgeState.UNKNOWN
        ),
        currently_visible=visible,
        position=facts.last_known_position,
        size=facts.size,
        appearance=(
            _observe_appearance(facts.appearance)
            if facts.appearance is not None
            else None
        ),
        health_band=facts.health_band,
        observed_damage_total=facts.observed_damage_total if known else None,
        known_conditions=facts.conditions,
        known_effects=facts.effects,
        observed_capability_ids=facts.observed_capability_ids,
    )


def _observe_ally(
    state: EncounterState,
    creature_ref: str,
    knowledge: TeamKnowledge,
) -> PlayerCreatureObservation:
    creature_state = state.creatures[creature_ref]
    creature = creature_state.creature
    facts = knowledge.facts_for(creature_ref)
    maximum_health = rule_queries.effective_maximum_health(
        state,
        creature_ref,
    ).value
    movement = rule_queries.movement_budget(state, creature_ref)
    remaining = (
        creature_state.movement_remaining
        if creature_state.movement_remaining is not None
        else movement.budget
    )
    return PlayerCreatureObservation(
        creature_ref=creature_ref,
        allegiance=CreatureAllegiance.ALLY,
        knowledge=KnowledgeState.ALLY_SHARED,
        currently_visible=True,
        position=facts.last_known_position,
        size=creature.size,
        appearance=_observe_appearance(creature.observable_appearance),
        health_band=_health_band(creature.get_health(), maximum_health),
        observed_damage_total=None,
        known_conditions=facts.conditions,
        known_effects=facts.effects,
        observed_capability_ids=(),
        health=creature.get_health(),
        maximum_health=maximum_health,
        temporary_hit_points=creature.temporary_hit_points,
        armor_class=rule_queries.effective_armor_class(state, creature_ref).value,
        action_available=creature_state.actions_remaining > 0,
        bonus_action_available=creature_state.bonus_action_available,
        reaction_available=rule_queries.reaction_eligibility(
            state,
            creature_ref,
        ).allowed,
        movement_remaining_feet=state.definition.grid.feet_for_squares(remaining),
        actions_remaining=creature_state.actions_remaining,
        attacks_remaining=creature_state.attacks_remaining,
        attacks_per_attack_action=rule_queries.attack_limit(
            state, creature_ref, creature.combat_profile.attacks_per_attack_action
        ).value,
        spell_slots=observe_spell_slots(creature),
        spell_capabilities=observe_spell_capabilities(creature),
        resource_pools=observe_resource_pools(creature),
        concentrating_on=tuple(
            dict.fromkeys(
                effect.identity.source.definition_id
                for effect in state.ongoing_effects
                if effect.kind is OngoingEffectKind.CONCENTRATION
                and effect.identity.source.applied_by_ref == creature_ref
            )
        ),
    )


def _observe_appearance(appearance: ObservableAppearance) -> AppearanceObservation:
    return AppearanceObservation(
        armor_label=appearance.armor_label,
        armor_category=appearance.armor_category.value,
        has_shield=appearance.has_shield,
        visible_weapons=appearance.visible_weapons,
        spellcasting_focus_label=appearance.spellcasting_focus_label,
        spellcasting_focus_kind=appearance.spellcasting_focus_kind.value,
        obvious_features=appearance.obvious_features,
        apparent_creature_type=appearance.apparent_creature_type,
    )


def _observe_completion(
    read: SessionRead,
) -> EncounterCompletionObservation | None:
    if read.completion_message is None:
        return None
    if read.completion_reason is None:
        raise RuntimeError("A completed encounter requires a termination reason.")
    return EncounterCompletionObservation(
        message=read.completion_message,
        reason=read.completion_reason,
        winning_team_id=read.winning_team_id,
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
