"""Validate spell invocation and staged target-selection candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures.feature_rules import (
    spell_invocation_grant,
)
from srd_arena.domain.geometry import Position
from srd_arena.domain.spells.rules import (
    SpellActionPayload,
    spell_chooses_area_targets,
)

from ...encounter_models.actions import CreatureRef, EncounterAction
from ...rule_queries.obstructions import creature_has_line_of_effect_to_cell
from ..capability_support import (
    capability_runtime_issue,
    capability_selection_runtime_issue,
)
from ..option_discovery.spell_areas import spell_area_targets
from ..option_discovery.spellcasting import spell_cast_block_reason_for
from .common import target_requirement_failure
from .models import EligibilityFailure
from .spell_selection import check_staged_spell_selection
from .spell_targeting import spell_target_eligibility
from .teleportation import teleport_destination_failure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class SpellActionRule:
    """Check spell knowledge, resources, target requirements, and geometry."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate spell access, resources, targeting, and requirements.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.spells.rules import spell_action_payload
        >>> actor = Mock()
        >>> actor.creature.spellcasting = None
        >>> action = EncounterAction(
        ...     'Cast', 'spell', value=spell_action_payload('fireball')
        ... )
        >>> SpellActionRule().check(
        ...     Mock(creatures={'hero': actor}), 'hero', action).code
        'spellcasting_unavailable'
        """

        if action.kind != "spell" or not isinstance(
            action.value,
            SpellActionPayload,
        ):
            return None
        payload = action.value
        actor = state.creatures[actor_ref].creature
        if actor.spellcasting is None:
            return EligibilityFailure(
                "spellcasting_unavailable",
                "This creature cannot cast spells.",
            )
        spell_id = payload.spell_id
        grant = spell_invocation_grant(actor, payload.grant_id)
        if payload.grant_id is not None and grant is None:
            return EligibilityFailure(
                "spell_grant_unavailable",
                "This spell invocation is not available.",
            )
        spell = actor.spellcasting.spell_for_grant(spell_id, grant)
        if spell is None:
            return EligibilityFailure(
                "spell_unavailable",
                "This spell is not known.",
            )
        if spell.definition is not None:
            runtime_issue = capability_runtime_issue(
                spell.definition
            ) or capability_selection_runtime_issue(
                spell.definition,
                payload.selected_option,
            )
            if runtime_issue is not None:
                return EligibilityFailure(
                    runtime_issue.code,
                    runtime_issue.message,
                )
            teleport_failure = teleport_destination_failure(
                state,
                actor_ref,
                spell.definition,
                payload.aim_point,
                aim_committed=action.aim_committed,
            )
            if teleport_failure is not None:
                return teleport_failure
        reason = spell_cast_block_reason_for(
            state,
            actor.spellcasting,
            spell,
            action.cost,
            payload.slot_level,
            grant.consumes_spell_slot if grant is not None else True,
        )
        if reason is not None:
            return EligibilityFailure("spell_blocked", reason)
        for selected_target_ref in payload.target_refs:
            target = state.creatures.get(selected_target_ref)
            if target is None or not target.is_alive:
                return EligibilityFailure(
                    "target_unavailable",
                    "The target is not available.",
                )
            targeting = spell_target_eligibility(
                state,
                actor_ref,
                selected_target_ref,
                spell,
            )
            if not targeting.allowed:
                return targeting.failures[0]
            requirement_failure = target_requirement_failure(
                state,
                actor_ref,
                selected_target_ref,
                spell.target_requirements,
            )
            if requirement_failure is not None:
                return requirement_failure
        if spell.geometry_mode == "point_area" and payload.aim_point is not None:
            aim_position = Position(
                int(payload.aim_point[0]),
                int(payload.aim_point[1]),
            )
            if not creature_has_line_of_effect_to_cell(
                state,
                actor_ref,
                aim_position,
            ):
                return EligibilityFailure(
                    "aim_has_total_cover",
                    "The chosen point is behind Total Cover.",
                )
        if payload.aim_point is not None and not spell_chooses_area_targets(spell):
            for selected_target in spell_area_targets(
                state,
                actor,
                spell,
                aim_point=payload.aim_point,
            ):
                targeting = spell_target_eligibility(
                    state,
                    actor_ref,
                    selected_target.target_ref,
                    spell,
                )
                if not targeting.allowed:
                    return targeting.failures[0]
        if (
            spell.geometry_mode not in {"directional_area", "point_area"}
            and not payload.target_refs
            and payload.aim_point is None
        ):
            return EligibilityFailure(
                "target_unavailable",
                "No valid spell target is available.",
            )
        return None


class SpellTargetSelectionRule:
    """Check staged target counts, allocations, and changing eligibility."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Validate one staged target, allocation, or confirmation choice.

        >>> from unittest.mock import Mock
        >>> action = EncounterAction('Confirm', 'confirm_spell_targets')
        >>> SpellTargetSelectionRule().check(
        ...     Mock(interrupts=Mock(pending_spell_cast=None)), 'hero', action).code
        'spell_selection_unavailable'
        """

        if action.kind not in {
            "toggle_spell_target",
            "set_spell_resource_allocation",
            "confirm_spell_targets",
        }:
            return None
        return check_staged_spell_selection(state, actor_ref, action)
