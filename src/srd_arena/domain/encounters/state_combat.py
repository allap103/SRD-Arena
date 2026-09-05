"""Combat-derived queries owned by encounter state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import CombatTrait, Condition
from srd_arena.domain.effects.triggered import TriggeredEffect, matching_effects
from srd_arena.domain.geometry import Position
from srd_arena.domain.rolls.dice import D20RollMode, combine_roll_modes

from .attack_rules import proximity_attack_roll_mode
from .effect_lifecycle.removal import _remove_effect_target
from .encounter_models.actions import CreatureRef
from .encounter_models.state import LethalDamage
from .rule_queries.defenses import resolve_damage
from .rule_queries.rolls import roll_modifiers
from .rule_queries.visibility import creature_can_see_creature
from .spatial import creature_distance

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_combat_damage(
    state: EncounterState,
    creature_ref: CreatureRef,
    amount: int,
    damage_type: str | None = None,
    *,
    critical_hit: bool = False,
) -> int:
    """Apply defenses and retain context for any resulting defeat resolution."""

    creature = state.creatures[creature_ref].creature
    was_alive = creature.get_health() > 0
    resolved = resolve_damage(state, creature_ref, amount, damage_type)
    if creature.temporary_hit_points <= 0:
        for effect in tuple(state.ongoing_effects):
            if (
                creature_ref in effect.target_refs
                and effect.lifecycle.ends_when_temporary_hit_points_depleted
            ):
                _remove_effect_target(state, effect, creature_ref)
    pending = state.pending_lethal_damage.get(creature_ref)
    if (was_alive and creature.get_health() <= 0) or pending is not None:
        damage_types = (
            frozenset({resolved.damage_type})
            if resolved.damage_type is not None and resolved.taken > 0
            else frozenset()
        )
        state.pending_lethal_damage[creature_ref] = LethalDamage(
            amount=resolved.taken + (pending.amount if pending is not None else 0),
            damage_types=damage_types.union(
                pending.damage_types if pending is not None else ()
            ),
            critical_hit=critical_hit
            or (pending.critical_hit if pending is not None else False),
        )
    return resolved.applied


def attack_roll_mode_for(
    state: EncounterState,
    attacker_ref: CreatureRef,
    target_ref: CreatureRef,
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
    *,
    nearby_opponent_refs: tuple[CreatureRef, ...] = (),
    attack_ability: str | None = None,
) -> D20RollMode:
    """Resolve advantage or disadvantage for an attacker-target pair.

    >>> from types import SimpleNamespace
    >>> effective = SimpleNamespace(
    ...     has=lambda condition: False,
    ...     has_trait=lambda trait: False,
    ... )
    >>> profile = SimpleNamespace(intrinsic_rule_providers={})
    >>> state = SimpleNamespace(
    ...     effective_conditions_for=lambda ref: effective, conditions=[],
    ...     ongoing_effects=[],
    ...     definition=SimpleNamespace(terrain=()),
    ...     creatures={
    ...         "archer": SimpleNamespace(
    ...             position=Position(0, 0),
    ...             creature=SimpleNamespace(size="M", combat_profile=profile),
    ...         ),
    ...         "goblin": SimpleNamespace(
    ...             position=Position(2, 0),
    ...             creature=SimpleNamespace(size="M", combat_profile=profile),
    ...         ),
    ...     },
    ... )
    >>> attack_roll_mode_for(
    ...     state, "archer", "goblin", "ranged", Position(0, 0),
    ...     (Position(1, 0),),
    ... )
    'disadvantage'
    """

    modes: list[D20RollMode] = []
    if nearby_opponent_refs and attack_type == "ranged":
        base_mode: D20RollMode = (
            "disadvantage"
            if any(
                creature_distance(state, attacker_ref, opponent_ref) == 1
                for opponent_ref in nearby_opponent_refs
            )
            else "normal"
        )
    else:
        base_mode = proximity_attack_roll_mode(
            attack_type,
            attacker_position,
            nearby_opponent_positions,
        )
    if base_mode != "normal":
        modes.append(base_mode)
    if not creature_can_see_creature(state, attacker_ref, target_ref):
        modes.append("disadvantage")
    if not creature_can_see_creature(state, target_ref, attacker_ref):
        modes.append("advantage")
    modes.append(
        roll_modifiers(
            state,
            attacker_ref,
            "attack_roll",
            attack_ability,
            opposing_ref=target_ref,
        ).mode
    )
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
    attacker_is_nearby = (
        attacker_position is not None
        and creature_distance(state, attacker_ref, target_ref) <= 1
    )
    if attacker_is_nearby and target_effective.has_trait(
        CombatTrait.NEARBY_ATTACKERS_HAVE_ADVANTAGE
    ):
        modes.append("advantage")
    if not attacker_is_nearby and target_effective.has_trait(
        CombatTrait.DISTANT_ATTACKERS_HAVE_DISADVANTAGE
    ):
        modes.append("disadvantage")
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
    >>> state = SimpleNamespace(
    ...     effective_conditions_for=lambda ref: effective,
    ...     creatures={
    ...         "hero": SimpleNamespace(
    ...             position=Position(0, 0), creature=SimpleNamespace(size="M")
    ...         ),
    ...         "target": SimpleNamespace(
    ...             position=Position(1, 0), creature=SimpleNamespace(size="M")
    ...         ),
    ...     },
    ... )
    >>> providers = automatic_critical_provider_ids_for(state, "hero", "target")
    >>> providers
    ('paralyzed:spell',)
    """

    if creature_distance(state, attacker_ref, target_ref) != 1:
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
