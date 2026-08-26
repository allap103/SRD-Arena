"""Compose read-only application observations for game clients."""

from __future__ import annotations

from typing import Any, cast

from srd_arena.runtime.session import Session

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


def observe_session(session: Session) -> GameObservation:
    """Translate mutable engine state into a frontend-neutral snapshot."""

    scene_view = session.get_scene_view()
    state = session.encounter_state
    scene = observe_scene(scene_view, state)
    transition = (
        TransitionObservation(message=session.pending_scene_transition.message)
        if session.pending_scene_transition is not None
        else None
    )
    return GameObservation(
        scene=scene,
        encounter=_observe_encounter(session) if state is not None else None,
        transition=transition,
        requires_automatic_advance=(
            transition is None
            and state is not None
            and state.requires_automatic_advance()
        ),
    )


def _observe_encounter(session: Session) -> EncounterObservation:
    state = session.encounter_state
    if state is None:
        raise RuntimeError("Cannot observe an encounter before it has started.")
    exported = cast(dict[str, Any], state.export_state())
    creatures = cast(dict[str, dict[str, Any]], exported["creatures"])
    grid = cast(dict[str, int], exported["grid"])
    decision = cast(dict[str, Any], exported["decision"])
    initiative = cast(list[dict[str, Any]], exported["initiative"])
    ongoing_effects = cast(list[dict[str, Any]], exported["ongoing_effects"])

    return EncounterObservation(
        encounter_id=str(exported["encounter_id"]),
        grid=GridObservation(width=grid["width"], height=grid["height"]),
        round_number=int(exported["round_number"]),
        decision=DecisionObservation(
            id=str(decision["frame_id"]),
            kind=str(decision["kind"]),
            creature_ref=str(decision["creature_ref"]),
        ),
        creatures=tuple(
            _observe_creature(session, state, creature_ref, creature)
            for creature_ref, creature in creatures.items()
        ),
        initiative=tuple(
            InitiativeObservation(
                creature_ref=str(entry["creature_ref"]),
                total=int(entry["total"]),
            )
            for entry in initiative
        ),
        ongoing_effects=tuple(_observe_effect(effect) for effect in ongoing_effects),
        team_ids=tuple(team.id for team in session.current_encounter.teams),
        targeting=_observe_targeting(state),
    )


def _observe_targeting(state: Any) -> TargetingObservation | None:
    pending = state.pending_spell_cast
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
    session: Session,
    state: Any,
    creature_ref: str,
    creature: dict[str, Any],
) -> CreatureObservation:
    position = cast(dict[str, int], creature["position"])
    slots_max = cast(dict[str, int], creature["spell_slots_max"])
    slots_remaining = cast(dict[str, int], creature["spell_slots_remaining"])
    effective_conditions = cast(list[dict[str, Any]], creature["effective_conditions"])
    feature_definitions = state.creatures[
        creature_ref
    ].creature.combat_profile.feature_actions
    domain_creature = state.creatures[creature_ref].creature
    attributes = domain_creature.attributes
    return CreatureObservation(
        creature_ref=creature_ref,
        creature_id=str(creature["creature_id"]),
        name=str(creature["name"]),
        label=str(creature["label"]),
        token_image=cast(str | None, creature["token_image"]),
        team_id=str(creature["team_id"]),
        position=PositionObservation(x=position["x"], y=position["y"]),
        health=int(creature["health"]),
        max_health=int(creature["max_health"]),
        is_alive=bool(creature["is_alive"]),
        action_available=bool(creature["action_available"]),
        bonus_action_available=bool(creature["bonus_action_available"]),
        reaction_available=bool(creature["reaction_available"]),
        attacks_remaining=int(creature["attacks_remaining"]),
        attacks_per_attack_action=int(creature["attacks_per_attack_action"]),
        movement_remaining=int(creature["movement_remaining"]),
        movement_total=int(creature["movement_total"]),
        movement_remaining_feet=int(creature["movement_remaining_feet"]),
        movement_total_feet=int(creature["movement_total_feet"]),
        effective_conditions=tuple(
            dict.fromkeys(
                str(condition["condition"]) for condition in effective_conditions
            )
        ),
        spell_slots=tuple(
            SpellSlotObservation(
                level=int(level),
                remaining=int(slots_remaining.get(level, maximum)),
                maximum=maximum,
            )
            for level, maximum in sorted(
                slots_max.items(), key=lambda item: int(item[0])
            )
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
        armor_class=int(creature["armor_class"]),
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
                name=(
                    session.item_templates[item_id].name
                    if item_id in session.item_templates
                    else item_id
                ),
            )
            for item_id in domain_creature.inventory.items
        ),
    )


def _observe_effect(effect: dict[str, Any]) -> OngoingEffectObservation:
    source = cast(dict[str, Any], effect["source"])
    parameters = cast(dict[str, Any], effect["parameters"])
    definition_id = str(source["definition_id"])
    explicit_label = parameters.get("effect_label")
    label = (
        explicit_label
        if isinstance(explicit_label, str) and explicit_label.strip()
        else definition_id.replace("_", " ").replace("-", " ").title()
    )
    return OngoingEffectObservation(
        kind=str(effect["kind"]),
        polarity=str(effect["polarity"]),
        applied_by_ref=cast(str | None, source.get("applied_by_ref")),
        definition_id=definition_id,
        target_refs=tuple(str(ref) for ref in effect["target_refs"]),
        label=label,
    )
