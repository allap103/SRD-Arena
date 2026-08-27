"""Validate spell invocation and staged target-selection candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_targets,
    parse_spell_action_value,
    spell_chooses_area_targets,
)
from ...models import CreatureRef, EncounterAction
from .common import target_requirement_failure
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class SpellActionRule:
    """Check spell knowledge, resources, target requirements, and chosen geometry."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate spell access, resources, targeting, and requirements.

        >>> from unittest.mock import Mock
        >>> actor = Mock()
        >>> actor.creature.spellcasting = None
        >>> action = EncounterAction("Cast", "spell", value="fireball")
        >>> SpellActionRule().check(
        ...     Mock(creatures={"hero": actor}), "hero", action).code
        'spellcasting_unavailable'
        """
        if action.kind != "spell" or not isinstance(action.value, str):
            return None
        actor = state.creatures[actor_ref].creature
        if actor.spellcasting is None:
            return EligibilityFailure(
                "spellcasting_unavailable",
                "This creature cannot cast spells.",
            )
        spell_id, target_ref, aim_point = parse_spell_action_value(action.value)
        spell = next(
            (
                known
                for known in actor.spellcasting.learned_spells
                if known.id == spell_id
            ),
            None,
        )
        if spell is None:
            return EligibilityFailure(
                "spell_unavailable",
                "This spell is not known.",
            )
        reason = state._spell_cast_block_reason(
            actor.spellcasting,
            spell,
            action.cost,
            parse_spell_action_slot(action.value),
        )
        if reason is not None:
            return EligibilityFailure("spell_blocked", reason)
        selected_target_refs = parse_spell_action_targets(action.value)
        for selected_target_ref in selected_target_refs:
            target = state.creatures.get(selected_target_ref)
            if target is None or not target.is_alive:
                return EligibilityFailure(
                    "target_unavailable", "The target is not available."
                )
            requirement_failure = target_requirement_failure(
                state,
                actor_ref,
                selected_target_ref,
                spell.target_requirements,
            )
            if requirement_failure is not None:
                return requirement_failure
        if (
            spell.geometry_mode not in {"directional_area", "point_area"}
            and target_ref is None
            and aim_point is None
        ):
            return EligibilityFailure(
                "target_unavailable",
                "No valid spell target is available.",
            )
        return None


class SpellTargetSelectionRule:
    """Check staged target counts, allocations, and changing target eligibility."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate staged spell target and resource-allocation choices.

        >>> from unittest.mock import Mock
        >>> action = EncounterAction("Confirm", "confirm_spell_targets")
        >>> SpellTargetSelectionRule().check(
        ...     Mock(pending_spell_cast=None), "hero", action).code
        'spell_selection_unavailable'
        """
        if action.kind not in {
            "toggle_spell_target",
            "set_spell_resource_allocation",
            "confirm_spell_targets",
        }:
            return None
        pending = state.pending_spell_cast
        if pending is None:
            return EligibilityFailure(
                "spell_selection_unavailable",
                "No spell target selection is active.",
            )
        actor = state.creatures[actor_ref].creature
        spell = (
            next(
                (
                    known
                    for known in actor.spellcasting.learned_spells
                    if known.id == pending.spell_id
                ),
                None,
            )
            if actor.spellcasting is not None
            else None
        )
        if spell is None:
            return EligibilityFailure(
                "spell_unavailable",
                "The staged spell is no longer available.",
            )
        _pending_spell_id, _pending_target, aim_point = parse_spell_action_value(
            str(pending.action.value)
        )
        candidate_refs = {
            target.target_ref
            for target in (
                state._spell_area_targets(actor, spell, aim_point=aim_point)
                if spell_chooses_area_targets(spell)
                else tuple(state._spell_action_targets(actor, spell))
            )
        }
        if action.kind == "toggle_spell_target":
            if not isinstance(action.value, str):
                return EligibilityFailure(
                    "target_required",
                    "A creature target is required.",
                )
            remove_target = action.id.endswith("-remove")
            if remove_target:
                if action.value not in pending.selected_target_refs:
                    return EligibilityFailure(
                        "target_unavailable",
                        "That target has no allocated spell effect to remove.",
                    )
                return None
            if (
                not pending.repeat_target_allocations
                and action.value in pending.selected_target_refs
            ):
                return None
            if len(pending.selected_target_refs) >= pending.maximum_targets:
                return EligibilityFailure(
                    "target_limit_reached",
                    "The spell's target limit has been reached.",
                )
            if action.value not in candidate_refs:
                return EligibilityFailure(
                    "target_unavailable",
                    "The target is not available for this spell.",
                )
            return target_requirement_failure(
                state,
                actor_ref,
                action.value,
                spell.target_requirements,
            )
        if action.kind == "set_spell_resource_allocation":
            if pending.resource_pool_total is None or not isinstance(action.value, str):
                return EligibilityFailure(
                    "spell_allocation_unavailable",
                    "No spell resource allocation is active.",
                )
            target_ref, separator, amount_text = action.value.rpartition("~")
            if not separator or not amount_text.isdigit():
                return EligibilityFailure(
                    "invalid_allocation",
                    "The allocation must provide a target and whole-number amount.",
                )
            amount = int(amount_text)
            limit = pending.resource_allocation_limits.get(target_ref)
            other_total = sum(
                value
                for ref, value in pending.resource_allocations.items()
                if ref != target_ref
            )
            if limit is None or amount > limit:
                return EligibilityFailure(
                    "invalid_allocation",
                    "The allocation exceeds that target's missing Hit Points.",
                )
            if other_total + amount > pending.resource_pool_total:
                return EligibilityFailure(
                    "resource_pool_exceeded",
                    "The allocation exceeds the remaining healing pool.",
                )
            return target_requirement_failure(
                state,
                actor_ref,
                target_ref,
                spell.target_requirements,
            )
        if (
            action.kind == "confirm_spell_targets"
            and pending.resource_pool_total is not None
        ):
            if not pending.resource_allocations:
                return EligibilityFailure(
                    "target_required",
                    "Allocate at least 1 Hit Point before casting.",
                )
            return None
        if not pending.selected_target_refs:
            return EligibilityFailure(
                "target_required",
                "Select at least one spell target.",
            )
        if (
            pending.require_full_target_count
            and len(pending.selected_target_refs) != pending.maximum_targets
        ):
            return EligibilityFailure(
                "target_allocation_incomplete",
                "Allocate every spell effect before casting.",
            )
        for target_ref in pending.selected_target_refs:
            if target_ref not in candidate_refs:
                return EligibilityFailure(
                    "target_unavailable",
                    "A selected target is no longer available for this spell.",
                )
            failure = target_requirement_failure(
                state,
                actor_ref,
                target_ref,
                spell.target_requirements,
            )
            if failure is not None:
                return failure
        return None
