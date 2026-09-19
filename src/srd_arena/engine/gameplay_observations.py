"""Capture gameplay facts once; information projections consume detached data."""

from srd_arena.domain.effects.runtime import OngoingEffectKind
from srd_arena.domain.encounters.event_visibility import event_visibility

from .gameplay_observation_models import (
    GameplayConditionObservation,
    GameplayCreatureObservation,
    GameplayEffectObservation,
    GameplayEventObservation,
    GameplayObservation,
    GameplayTeamObservation,
)
from .observability import condition_observability, effect_observability
from .observations import observe_game_state
from .player_decision_observations import observe_player_decision
from .player_movement_observations import player_movement_observations
from .player_observation_models import AppearanceObservation
from .queries import SessionRead
from .spell_capability_observations import observe_spell_capabilities
from .targeting_observations import observe_player_targeting

GAMEPLAY_OBSERVATION_SCHEMA_ID = "gameplay-observation-v2-draft"


def capture_gameplay(
    read: SessionRead,
    *,
    history: tuple[GameplayEventObservation, ...] = (),
    episode_id: tuple[int, int] = (0, 0),
) -> GameplayObservation:
    """Capture immutable current facts and a retained episode event prefix."""

    game = observe_game_state(read)
    state = read.encounter_state
    if state is None:
        return GameplayObservation(
            GAMEPLAY_OBSERVATION_SCHEMA_ID,
            episode_id,
            game,
            (),
            (),
            history,
            (),
            None,
            False,
            (),
        )
    assert game.encounter is not None
    creatures: list[GameplayCreatureObservation] = []
    for combat in game.encounter.creatures:
        ref = combat.creature_ref
        participant = state.creatures[ref]
        creature = participant.creature
        appearance = creature.observable_appearance
        creatures.append(
            GameplayCreatureObservation(
                combat=combat,
                appearance=AppearanceObservation(
                    armor_label=appearance.armor_label,
                    armor_category=appearance.armor_category.value,
                    has_shield=appearance.has_shield,
                    visible_weapons=appearance.visible_weapons,
                    spellcasting_focus_label=appearance.spellcasting_focus_label,
                    spellcasting_focus_kind=appearance.spellcasting_focus_kind.value,
                    obvious_features=appearance.obvious_features,
                    apparent_creature_type=appearance.apparent_creature_type,
                ),
                actions_remaining=participant.actions_remaining,
                spell_slot_spent_this_turn=ref in state.turn.spell_slot_users,
                bonus_action_available=participant.bonus_action_available,
                concentrating_on=tuple(
                    dict.fromkeys(
                        effect.identity.source.definition_id
                        for effect in state.ongoing_effects
                        if effect.kind is OngoingEffectKind.CONCENTRATION
                        and effect.identity.source.applied_by_ref == ref
                    )
                ),
                spell_capabilities=observe_spell_capabilities(creature),
                conditions=tuple(
                    GameplayConditionObservation(
                        applied.condition.value,
                        tuple(applied.provider_ids),
                        condition_observability(applied.condition),
                    )
                    for applied in state.effective_conditions_for(ref).conditions
                ),
                effects=tuple(
                    GameplayEffectObservation(
                        effect.identity.id,
                        effect.identity.source.definition_id,
                        effect.label or effect.identity.source.definition_id,
                        effect_observability(effect),
                    )
                    for effect in state.ongoing_effects
                    if ref in effect.target_refs
                ),
            )
        )
    visibility = dict(event_visibility(state))
    decision = state.current_decision()
    teams: list[GameplayTeamObservation] = []
    for team_id in read.team_ids:
        allies = frozenset(
            ref for ref, team in read.creature_team_ids.items() if team == team_id
        )
        visible = visibility.get(team_id, frozenset()) | allies
        teams.append(
            GameplayTeamObservation(
                team_id=team_id,
                visible_creature_refs=visible,
                movement_actions=player_movement_observations(
                    game.scene.action_details,
                    state,
                    visible,
                )
                if decision.creature_ref in allies
                else (),
                targeting=observe_player_targeting(state, allies),
                decision_context=observe_player_decision(
                    decision,
                    allied_refs=allies,
                    visible_refs=visible,
                ),
            )
        )
    return GameplayObservation(
        schema_id=GAMEPLAY_OBSERVATION_SCHEMA_ID,
        episode_id=episode_id,
        game=game,
        creatures=tuple(creatures),
        teams=tuple(teams),
        history=history,
        initiative_order=tuple(state.initiative_order),
        active_turn_ref=state.initiative_order[state.turn.index],
        sunlight=state.definition.environment.sunlight,
        terrain_movement_modes=tuple(
            (cell.position.x, cell.position.y, cell.movement_mode.value)
            for cell in state.definition.terrain
        ),
    )
