"""Begin spell actions and open pre-invocation target selection when required."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....capabilities import HealingEffect, capability_effects
from ....spells.rules import (
    parse_spell_action_ability,
    parse_spell_action_condition,
    parse_spell_action_damage_type,
    parse_spell_action_slot,
    parse_spell_action_targets,
    parse_spell_action_value,
    spell_action_value,
    spell_chooses_area_targets,
    spell_max_targets,
    spell_repeats_target_allocations,
    spell_requires_full_target_count,
)
from ...models import (
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
    PendingSpellCast,
)

if TYPE_CHECKING:
    from ....creatures import Creature
    from ...encounter import EncounterState


def execute_spell_invocation(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve a complete cast or suspend it before casting for target choices.

    >>> from types import SimpleNamespace
    >>> execute_spell_invocation(
    ...     SimpleNamespace(), SimpleNamespace(), EncounterAction("Cast", "spell"),
    ...     DecisionFrame("turn", "mage", "turn", "active"),
    ...     EncounterProgress(), "cast-1"
    ... )
    Traceback (most recent call last):
    ...
    ValueError: Spell action requires a spell payload.
    """

    if not isinstance(action.value, str):
        raise ValueError("Spell action requires a spell payload.")
    spell_id, _target_ref, aim_point = parse_spell_action_value(action.value)
    spell = (
        next(
            candidate
            for candidate in actor.spellcasting.learned_spells
            if candidate.id == spell_id
        )
        if actor.spellcasting is not None
        else None
    )
    maximum_targets = (
        spell_max_targets(
            spell,
            parse_spell_action_slot(action.value),
            caster_level=actor.attributes.level,
        )
        if spell is not None
        else 1
    )
    repeat_target_allocations = bool(
        spell is not None and spell_repeats_target_allocations(spell)
    )
    require_full_target_count = bool(
        spell is not None and spell_requires_full_target_count(spell)
    )
    resource_pool_total = next(
        (
            effect.pool
            for effect in capability_effects(
                spell.definition if spell is not None else None
            )
            if isinstance(effect, HealingEffect) and effect.pool is not None
        ),
        None,
    )
    selected_targets = list(parse_spell_action_targets(action.value))
    resource_allocation_limits: dict[str, int] = {}
    if resource_pool_total is not None and spell is not None:
        resource_allocation_limits = {
            target.target_ref: (
                target.creature.get_max_health() - target.creature.get_health()
            )
            for target in state._spell_action_targets(actor, spell)
            if target.creature.get_health() < target.creature.get_max_health()
        }
        selected_targets = []
        maximum_targets = len(resource_allocation_limits)
    if (
        spell is not None
        and spell_chooses_area_targets(spell)
        and aim_point is not None
    ):
        area_target_refs = [
            target.target_ref
            for target in state._spell_area_targets(
                actor,
                spell,
                aim_point=aim_point,
            )
        ]
        selects_every_occupant = bool(
            spell.definition is not None
            and spell.definition.target.count.maximum == "all"
        )
        maximum_targets = (
            len(area_target_refs)
            if selects_every_occupant
            else min(maximum_targets, len(area_target_refs))
        )
        selected_targets = area_target_refs[:maximum_targets]
    staged_selection_needed = (
        resource_pool_total is not None
        or (maximum_targets > 1 and bool(selected_targets))
        or (
            spell is not None
            and spell_chooses_area_targets(spell)
            and len(selected_targets) > 1
        )
    )
    automated_resolved = False
    if (
        staged_selection_needed
        and state._creature_controller(decision.creature_ref) != "external"
        and spell is not None
    ):
        if repeat_target_allocations:
            target_ref = selected_targets[0]
            selected_targets = [target_ref] * maximum_targets
        elif resource_pool_total is not None:
            healing_remaining = resource_pool_total
            allocations: dict[str, int] = {}
            for target_ref, candidate_limit in resource_allocation_limits.items():
                amount = min(candidate_limit, healing_remaining)
                if amount > 0:
                    allocations[target_ref] = amount
                    healing_remaining -= amount
                if healing_remaining == 0:
                    break
            automated_payload = spell_action_value(
                spell_id,
                tuple(allocations),
                aim_point=aim_point,
                slot_level=parse_spell_action_slot(action.value),
                healing_allocations=allocations,
            )
            state._resolve_spell_action(
                actor,
                automated_payload,
                progress,
                action_id,
            )
            staged_selection_needed = False
            automated_resolved = True
        elif not spell_chooses_area_targets(spell):
            selected_targets = [
                target.target_ref
                for target in state._spell_action_targets(
                    actor,
                    spell,
                )[:maximum_targets]
            ]
        if not automated_resolved:
            automated_payload = spell_action_value(
                spell_id,
                tuple(selected_targets),
                aim_point=aim_point,
                selected_condition=parse_spell_action_condition(action.value),
                selected_damage_type=parse_spell_action_damage_type(action.value),
                selected_ability=parse_spell_action_ability(action.value),
                slot_level=parse_spell_action_slot(action.value),
            )
            state._resolve_spell_action(
                actor,
                automated_payload,
                progress,
                action_id,
            )
            staged_selection_needed = False
            automated_resolved = True
    if staged_selection_needed:
        state.pending_spell_cast = PendingSpellCast(
            action=action,
            spell_id=spell_id,
            selected_target_refs=selected_targets,
            maximum_targets=maximum_targets,
            repeat_target_allocations=repeat_target_allocations,
            require_full_target_count=require_full_target_count,
            resource_pool_total=resource_pool_total,
            resource_allocation_limits=resource_allocation_limits,
        )
        state.decision_stack.append(
            DecisionFrame(
                id=f"spell-targets-{action_id}",
                creature_ref=decision.creature_ref,
                kind="spell_targets",
                reason=(
                    f"Allocate {maximum_targets} spell effects."
                    if require_full_target_count
                    else f"Choose up to {maximum_targets} spell targets."
                ),
                parent_frame_id=decision.id,
                parent_action_id=action_id,
            )
        )
        progress.paused_for_decision = True
    elif not automated_resolved:
        state._resolve_spell_action(
            actor,
            action.value,
            progress,
            action_id,
        )
