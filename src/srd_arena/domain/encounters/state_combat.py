"""Combat-derived queries owned by encounter state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import CombatTrait, Condition
from srd_arena.domain.effects.triggered import TriggeredEffect, matching_effects
from srd_arena.domain.geometry import Position
from srd_arena.domain.rolls.dice import D20RollMode, combine_roll_modes

from .attack_rules import proximity_attack_roll_mode
from .behaviors import is_adjacent
from .encounter_models.actions import CreatureRef
from .rule_queries.rolls import roll_modifiers
from .state_runtime import creature_position

if TYPE_CHECKING:
    from .encounter import EncounterState


def attack_roll_mode_for(
    state: EncounterState,
    attacker_ref: CreatureRef,
    target_ref: CreatureRef,
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    """Resolve advantage or disadvantage for an attacker-target pair.

    >>> from types import SimpleNamespace
    >>> effective = SimpleNamespace(
    ...     has_trait=lambda trait: False
    ... )
    >>> state = SimpleNamespace(
    ...     effective_conditions_for=lambda ref: effective, conditions=[],
    ...     ongoing_effects=[],
    ... )
    >>> attack_roll_mode_for(
    ...     state, "archer", "goblin", "ranged", Position(0, 0),
    ...     (Position(1, 0),),
    ... )
    'disadvantage'
    """

    modes: list[D20RollMode] = []
    base_mode = proximity_attack_roll_mode(
        attack_type,
        attacker_position,
        nearby_opponent_positions,
    )
    if base_mode != "normal":
        modes.append(base_mode)
    target_effective = state.effective_conditions_for(target_ref)
    modes.append(
        roll_modifiers(
            state,
            target_ref,
            "attack_roll",
            subject="attacks_against_target",
            opposing_ref=attacker_ref,
        ).mode
    )
    if target_effective.has_trait(CombatTrait.ATTACKERS_HAVE_ADVANTAGE):
        modes.append("advantage")
    context = {
        "attacker_ref": attacker_ref,
        "target_ref": target_ref,
        "attack_type": attack_type,
    }
    if any(
        condition.condition is Condition.GRAPPLED
        and condition.target_ref == attacker_ref
        and condition.source_ref != target_ref
        for condition in state.conditions
    ):
        modes.append("disadvantage")
    for effect in matching_effects(
        active_status_effects(state),
        "attack_roll_created",
        context,
    ):
        if effect.operation == "grant_advantage":
            modes.append("advantage")
        elif effect.operation == "grant_disadvantage":
            modes.append("disadvantage")
    return combine_roll_modes(*modes)


def automatic_critical_provider_ids_for(
    state: EncounterState,
    attacker_ref: CreatureRef,
    target_ref: CreatureRef,
) -> tuple[str, ...]:
    """Return active rules that make a qualifying hit automatically critical.

    >>> from types import SimpleNamespace
    >>> effective = SimpleNamespace(
    ...     providers_for_trait=lambda trait: ("paralyzed:spell",)
    ... )
    >>> positions = {"hero": Position(0, 0), "target": Position(1, 0)}
    >>> state = SimpleNamespace(effective_conditions_for=lambda ref: effective)
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.state_combat.creature_position",
    ...     side_effect=lambda state, ref: positions[ref],
    ... ):
    ...     providers = automatic_critical_provider_ids_for(state, "hero", "target")
    >>> providers
    ('paralyzed:spell',)
    """

    if not is_adjacent(
        creature_position(state, attacker_ref),
        creature_position(state, target_ref),
    ):
        return ()
    return state.effective_conditions_for(target_ref).providers_for_trait(
        CombatTrait.HITS_WITHIN_5_FEET_ARE_CRITICAL
    )


def automatic_save_failure_provider_ids_for(
    state: EncounterState,
    target_ref: CreatureRef,
    ability: str,
) -> tuple[str, ...]:
    """Return active rules that force a creature to fail the specified save.

    >>> from types import SimpleNamespace
    >>> effective = SimpleNamespace(
    ...     providers_for_trait=lambda trait: ("stunned:monk",)
    ... )
    >>> state = SimpleNamespace(effective_conditions_for=lambda ref: effective)
    >>> automatic_save_failure_provider_ids_for(state, "target", "dexterity")
    ('stunned:monk',)
    >>> automatic_save_failure_provider_ids_for(state, "target", "wisdom")
    ()
    """

    trait = {
        "strength": CombatTrait.AUTO_FAIL_STRENGTH_SAVES,
        "dexterity": CombatTrait.AUTO_FAIL_DEXTERITY_SAVES,
    }.get(ability)
    if trait is None:
        return ()
    return state.effective_conditions_for(target_ref).providers_for_trait(trait)


def active_status_effects(state: EncounterState) -> list[TriggeredEffect]:
    """Return triggered rules exposed by all active conditions.

    >>> from types import SimpleNamespace
    >>> effect = TriggeredEffect("e", "condition", "prone", "hit", "notify")
    >>> state = SimpleNamespace(
    ...     conditions=[SimpleNamespace(triggered_effects=(effect,))]
    ... )
    >>> active_status_effects(state)
    [TriggeredEffect(id='e', source_type='condition', source_id='prone', trigger='hit', operation='notify', conditions={}, parameters={})]
    """

    return [
        effect for status in state.conditions for effect in status.triggered_effects
    ]
