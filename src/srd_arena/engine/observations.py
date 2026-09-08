"""Compose immutable engine observations for game clients."""

from __future__ import annotations

from srd_arena.domain.effects.runtime import OngoingEffect
from srd_arena.domain.encounters import rule_queries
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.spatial import creature_occupied_cells
from srd_arena.domain.geometry import serialize_area
from srd_arena.engine.protocols import GameEngine
from srd_arena.engine.queries import SessionRead

from .action_observations import observe_scene
from .observation_models import (
    ActionObservation,
    ActionReasonObservation,
    AttributeObservation,
    CreatureDefenseObservation,
    CreatureObservation,
    CreatureRelationshipObservation,
    DecisionObservation,
    EncounterCompletionObservation,
    EncounterObservation,
    EncounterTerminationReason,
    FeatureActionObservation,
    GameObservation,
    GridObservation,
    InitiativeObservation,
    InventoryItemObservation,
    OngoingEffectObservation,
    PositionObservation,
    ResourcePoolObservation,
    SceneObservation,
    SpellSlotObservation,
    TargetingObservation,
    TargetResourceAllocationObservation,
    TargetResourceLimitObservation,
    TerrainCellObservation,
)
from .resource_observations import observe_resource_pools, observe_spell_slots
from .targeting_observations import observe_targeting
from .values import freeze_mapping

__all__ = [
    "ActionObservation",
    "ActionReasonObservation",
    "AttributeObservation",
    "CreatureDefenseObservation",
    "CreatureObservation",
    "CreatureRelationshipObservation",
    "DecisionObservation",
    "EncounterCompletionObservation",
    "EncounterObservation",
    "EncounterTerminationReason",
    "FeatureActionObservation",
    "GameObservation",
    "GridObservation",
    "InitiativeObservation",
    "InventoryItemObservation",
    "OngoingEffectObservation",
    "PositionObservation",
    "ResourcePoolObservation",
    "SceneObservation",
    "SpellSlotObservation",
    "TargetResourceAllocationObservation",
    "TargetResourceLimitObservation",
    "TargetingObservation",
    "TerrainCellObservation",
    "observe_session",
]


def observe_session(session: GameEngine) -> GameObservation:
    """Translate mutable engine state into a frontend-neutral snapshot.

    >>> from types import SimpleNamespace
    >>> read = SessionRead(
    ...     scene_id="intro", action_options=(),
    ...     encounter_state=None, completion_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> observation = observe_session(SimpleNamespace(_read=lambda: read))
    >>> (observation.scene.scene_id, observation.encounter)
    ('intro', None)
    """

    read = session._read()
    state = read.encounter_state
    scene = observe_scene(read)
    completion = None
    if read.completion_message is not None:
        if read.completion_reason is None:
            raise RuntimeError("A completed encounter requires a termination reason.")
        completion = EncounterCompletionObservation(
            message=read.completion_message,
            reason=read.completion_reason,
            winning_team_id=read.winning_team_id,
        )
    return GameObservation(
        scene=scene,
        encounter=_observe_encounter(read) if state is not None else None,
        completion=completion,
        requires_automatic_advance=read.requires_automatic_advance,
    )


def _observe_encounter(read: SessionRead) -> EncounterObservation:
    state = read.encounter_state
    if state is None:
        raise RuntimeError("Cannot observe an encounter before it has started.")
    grid = state.definition.grid
    decision = state.current_decision()

    return EncounterObservation(
        encounter_id=state.encounter_id,
        grid=GridObservation(width=grid.width, height=grid.height),
        round_number=state.round.number,
        decision=DecisionObservation(
            id=f"{decision.id}@{read.decision_epoch}:{read.decision_revision}",
            kind=decision.kind,
            creature_ref=decision.creature_ref,
        ),
        creatures=tuple(
            _observe_creature(read, state, creature_ref, creature_state)
            for creature_ref, creature_state in state.creatures.items()
        ),
        initiative=tuple(
            InitiativeObservation(
                creature_ref=entry.creature_ref,
                total=entry.total,
            )
            for entry in state.initiative_entries
        ),
        ongoing_effects=tuple(
            _observe_effect(effect) for effect in state.ongoing_effects
        ),
        team_ids=read.team_ids,
        targeting=observe_targeting(state),
        relationships=tuple(
            CreatureRelationshipObservation(
                id=relationship.identity.id,
                kind=relationship.kind.value,
                source_ref=relationship.source_ref,
                target_ref=relationship.target_ref,
                source_definition_id=relationship.identity.source.definition_id,
            )
            for relationship in state.relationships
        ),
        terrain=tuple(
            TerrainCellObservation(
                position=PositionObservation(
                    x=terrain.position.x,
                    y=terrain.position.y,
                ),
                traversal=terrain.traversal.value,
                cover=terrain.cover.value,
            )
            for terrain in state.definition.terrain
        ),
    )


def _observe_creature(
    read: SessionRead,
    state: EncounterState,
    creature_ref: str,
    creature_state: EncounterCreatureState,
) -> CreatureObservation:
    creature = creature_state.creature
    attributes = creature.attributes
    feature_definitions = creature.combat_profile.feature_actions
    movement = rule_queries.movement_budget(state, creature_ref)
    movement_remaining = (
        creature_state.movement_remaining
        if creature_state.movement_remaining is not None
        else movement.budget
    )
    action_available = rule_queries.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            label="Action",
            kind="action",
            creature_ref=creature_ref,
            cost=ActionCost(action=1),
        ),
    ).allowed
    bonus_action_available = rule_queries.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            label="Bonus Action",
            kind="bonus_action",
            creature_ref=creature_ref,
            cost=ActionCost(bonus_action=1),
        ),
    ).allowed
    reaction_available = rule_queries.reaction_eligibility(
        state,
        creature_ref,
    ).allowed
    attacks_per_attack_action = rule_queries.attack_limit(
        state,
        creature_ref,
        creature.combat_profile.attacks_per_attack_action,
    ).value
    effective_conditions = state.effective_conditions_for(creature_ref).conditions
    armor_class = rule_queries.effective_armor_class(
        state,
        creature_ref,
    ).value
    return CreatureObservation(
        creature_ref=creature_ref,
        creature_id=creature_state.creature_id,
        name=creature.name,
        label=read.creature_labels[creature_ref],
        token_image=creature.token_image,
        team_id=read.creature_team_ids[creature_ref],
        position=PositionObservation(
            x=creature_state.position.x,
            y=creature_state.position.y,
        ),
        health=creature.get_health(),
        max_health=rule_queries.effective_maximum_health(
            state,
            creature_ref,
        ).value,
        is_alive=creature_state.is_alive,
        action_available=action_available,
        bonus_action_available=bonus_action_available,
        reaction_available=reaction_available,
        attacks_remaining=creature_state.attacks_remaining,
        attacks_per_attack_action=attacks_per_attack_action,
        movement_remaining=movement_remaining,
        movement_total=movement.budget,
        movement_remaining_feet=state.definition.grid.feet_for_squares(
            movement_remaining
        ),
        movement_total_feet=movement.speed.value,
        effective_conditions=tuple(
            dict.fromkeys(
                condition.condition.value for condition in effective_conditions
            )
        ),
        spell_slots=observe_spell_slots(creature),
        feature_actions=tuple(
            FeatureActionObservation(
                feature_id=definition.feature_id,
                label=definition.label,
                economy=definition.economy,
            )
            for definition in feature_definitions.values()
        ),
        armor_class=armor_class,
        attributes=AttributeObservation(
            level=attributes.level,
            strength=attributes.strength,
            dexterity=attributes.dexterity,
            constitution=attributes.constitution,
            wisdom=attributes.wisdom,
            intelligence=attributes.intelligence,
            charisma=attributes.charisma,
            proficiency_bonus=attributes.proficiency_bonus,
        ),
        inventory=tuple(
            InventoryItemObservation(
                item_id=item_id,
                name=read.item_names.get(item_id, item_id),
            )
            for item_id in creature.inventory.items
        ),
        temporary_hit_points=creature.temporary_hit_points,
        creature_type=creature.statistics.creature_type,
        type_tags=creature.statistics.type_tags,
        size=creature.size,
        occupied_cells=tuple(
            PositionObservation(
                x=cell.x,
                y=cell.y,
            )
            for cell in creature_occupied_cells(state, creature_ref)
        ),
        resource_pools=observe_resource_pools(creature),
        defenses=CreatureDefenseObservation(
            condition_immunities=tuple(
                sorted(
                    condition.value
                    for condition in rule_queries.condition_immunities(
                        state,
                        creature_ref,
                    ).values
                )
            ),
            damage_resistances=tuple(
                sorted(rule_queries.damage_resistances(state, creature_ref).values)
            ),
            damage_immunities=tuple(
                sorted(rule_queries.damage_immunities(state, creature_ref).values)
            ),
            damage_vulnerabilities=tuple(
                sorted(rule_queries.damage_vulnerabilities(state, creature_ref).values)
            ),
        ),
    )


def _observe_effect(effect: OngoingEffect) -> OngoingEffectObservation:
    source = effect.identity.source
    definition_id = source.definition_id
    label = effect.label or definition_id.replace("_", " ").replace("-", " ").title()
    area = serialize_area(effect.area)
    return OngoingEffectObservation(
        kind=effect.kind.value,
        polarity=effect.polarity.value,
        applied_by_ref=source.applied_by_ref,
        definition_id=definition_id,
        target_refs=effect.target_refs,
        label=label,
        area=freeze_mapping(area) if area is not None else None,
        obscures_vision=effect.obscures_vision,
    )
