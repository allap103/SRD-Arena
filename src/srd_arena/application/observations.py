"""Compose read-only application observations for game clients."""

from __future__ import annotations

from srd_arena.domain.effects.runtime import OngoingEffect
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.engine.api import GameEngine
from srd_arena.engine.queries import SessionRead

from .action_observations import observe_scene
from .observation_models import (
    ActionObservation,
    ActionReasonObservation,
    AttributeObservation,
    CreatureObservation,
    DecisionObservation,
    EncounterObservation,
    FeatureActionObservation,
    GameObservation,
    GridObservation,
    InitiativeObservation,
    InventoryItemObservation,
    OngoingEffectObservation,
    PositionObservation,
    SceneObservation,
    SpellSlotObservation,
    TargetingObservation,
    TargetResourceAllocationObservation,
    TargetResourceLimitObservation,
    TransitionObservation,
)

__all__ = [
    "ActionObservation",
    "ActionReasonObservation",
    "AttributeObservation",
    "CreatureObservation",
    "DecisionObservation",
    "EncounterObservation",
    "FeatureActionObservation",
    "GameObservation",
    "GridObservation",
    "InitiativeObservation",
    "InventoryItemObservation",
    "OngoingEffectObservation",
    "PositionObservation",
    "SceneObservation",
    "SpellSlotObservation",
    "TargetResourceAllocationObservation",
    "TargetResourceLimitObservation",
    "TargetingObservation",
    "TransitionObservation",
    "observe_session",
]


def observe_session(session: GameEngine) -> GameObservation:
    """Translate mutable engine state into a frontend-neutral snapshot.

    >>> from types import SimpleNamespace
    >>> read = SessionRead(
    ...     scene_id="intro", scene_text="Ready", action_options=(),
    ...     encounter_state=None, transition_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> observation = observe_session(SimpleNamespace(read=lambda: read))
    >>> (observation.scene.scene_id, observation.encounter)
    ('intro', None)
    """

    read = session.read()
    state = read.encounter_state
    scene = observe_scene(read)
    transition = (
        TransitionObservation(message=read.transition_message)
        if read.transition_message is not None
        else None
    )
    return GameObservation(
        scene=scene,
        encounter=_observe_encounter(read) if state is not None else None,
        transition=transition,
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
            id=decision.id,
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
        targeting=_observe_targeting(state),
    )


def _observe_targeting(state: EncounterState) -> TargetingObservation | None:
    pending = state.interrupts.pending_spell_cast
    if pending is None:
        return None
    actor = state.creatures[state.current_decision().creature_ref].creature
    spell = (
        next(
            (
                spell
                for spell in actor.spellcasting.learned_spells
                if spell.id == pending.spell_id
            ),
            None,
        )
        if actor.spellcasting is not None
        else None
    )
    return TargetingObservation(
        source_id=pending.spell_id,
        source_label=spell.name if spell is not None else pending.spell_id,
        selected_target_refs=tuple(pending.selected_target_refs),
        maximum_targets=pending.maximum_targets,
        repeat_target_allocations=pending.repeat_target_allocations,
        require_full_target_count=pending.require_full_target_count,
        resource_pool_total=pending.resource_pool_total,
        resource_allocations=tuple(
            TargetResourceAllocationObservation(target_ref=target_ref, amount=amount)
            for target_ref, amount in pending.resource_allocations.items()
        ),
        resource_limits=tuple(
            TargetResourceLimitObservation(target_ref=target_ref, maximum=maximum)
            for target_ref, maximum in pending.resource_allocation_limits.items()
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
    spellcasting = creature.spellcasting
    slots_max = spellcasting.spell_slots_max if spellcasting is not None else {}
    slots_remaining = (
        spellcasting.spell_slots_remaining if spellcasting is not None else {}
    )
    movement = state.combat_rules.movement_budget(state, creature_ref)
    movement_remaining = (
        creature_state.movement_remaining
        if creature_state.movement_remaining is not None
        else movement.budget
    )
    action_available = state.combat_rules.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            label="Action",
            kind="action",
            creature_ref=creature_ref,
            cost=ActionCost(action=1),
        ),
    ).allowed
    bonus_action_available = state.combat_rules.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            label="Bonus Action",
            kind="bonus_action",
            creature_ref=creature_ref,
            cost=ActionCost(bonus_action=1),
        ),
    ).allowed
    reaction_available = state.combat_rules.reaction_eligibility(
        state,
        creature_ref,
    ).allowed
    attacks_per_attack_action = state.combat_rules.attack_limit(
        state,
        creature_ref,
        creature.combat_profile.attacks_per_attack_action,
    ).value
    effective_conditions = state.effective_conditions_for(creature_ref).conditions
    armor_class = state.combat_rules.effective_armor_class(
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
        max_health=creature.get_max_health(),
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
        spell_slots=tuple(
            SpellSlotObservation(
                level=level,
                remaining=slots_remaining.get(level, maximum),
                maximum=maximum,
            )
            for level, maximum in sorted(slots_max.items())
            if maximum > 0
        ),
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
    )


def _observe_effect(effect: OngoingEffect) -> OngoingEffectObservation:
    source = effect.identity.source
    definition_id = source.definition_id
    explicit_label = effect.parameters.get("effect_label")
    label = (
        explicit_label
        if isinstance(explicit_label, str) and explicit_label.strip()
        else definition_id.replace("_", " ").replace("-", " ").title()
    )
    return OngoingEffectObservation(
        kind=effect.kind.value,
        polarity=effect.polarity.value,
        applied_by_ref=source.applied_by_ref,
        definition_id=definition_id,
        target_refs=effect.target_refs,
        label=label,
    )
