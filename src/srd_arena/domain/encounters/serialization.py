from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.conditions import AppliedCondition
from ..effects.runtime import (
    EffectDuration,
    EffectSource,
    Indefinite,
    Rounds,
    UntilTurnEnd,
    UntilTurnStart,
    WhileParentExists,
)
from .behaviors import movement_budget_for

if TYPE_CHECKING:
    from .encounter import EncounterState


def export_decision(self: EncounterState) -> dict[str, object]:
    decision = self.current_decision()
    payload: dict[str, object] = {
        "frame_id": decision.id,
        "creature_ref": decision.creature_ref,
        "kind": decision.kind,
        "reason": decision.reason,
        "can_pass": decision.can_pass,
        "parent_frame_id": decision.parent_frame_id,
        "parent_action_id": decision.parent_action_id,
    }
    if self.pending_movement is not None:
        payload["pending_movement_id"] = self.pending_movement.action_id
    return payload


def export_state(self: EncounterState) -> dict[str, object]:
    active_creature_ref = self.current_decision().creature_ref
    return {
        "encounter_id": self.encounter_id,
        "grid": {
            "width": self.definition.grid.width,
            "height": self.definition.grid.height,
        },
        "round_number": self.round_number,
        "turn_index": self.turn_index,
        "initiative_order": list(self.initiative_order),
        "initiative": [
            {
                "creature_ref": entry.creature_ref,
                "label": self._creature_label(entry.creature_ref),
                "roll": entry.roll,
                "modifier": entry.modifier,
                "total": entry.total,
            }
            for entry in self.initiative_entries
        ],
        "active_creature_ref": active_creature_ref,
        "active_controller": self._creature_controller(active_creature_ref),
        "creatures": {
            creature_ref: _export_creature(self, creature_ref)
            for creature_ref in self.creatures
        },
        "applied_conditions": [
            {
                "id": condition.id,
                "condition": condition.condition.value,
                "source": _export_source(condition.identity.source),
                "target_ref": condition.target_ref,
                "duration": _export_duration(condition.duration),
                "value": condition.value,
                "root_id": condition.identity.root_id,
                "parent_id": condition.identity.parent_id,
            }
            for condition in self.conditions
        ],
        "ongoing_effects": [
            {
                "id": effect.identity.id,
                "kind": effect.kind.value,
                "source": _export_source(effect.identity.source),
                "target_refs": list(effect.target_refs),
                "duration": _export_duration(effect.duration),
                "root_id": effect.identity.root_id,
                "parent_id": effect.identity.parent_id,
                "parameters": dict(effect.parameters),
                "dispellable": effect.dispellable,
                "tags": sorted(tag.value for tag in effect.tags),
            }
            for effect in self.ongoing_effects
        ],
        "relationships": [
            {
                "id": relationship.identity.id,
                "kind": relationship.kind.value,
                "source": _export_source(relationship.identity.source),
                "source_ref": relationship.source_ref,
                "target_ref": relationship.target_ref,
                "duration": _export_duration(relationship.duration),
                "root_id": relationship.identity.root_id,
                "parent_id": relationship.identity.parent_id,
            }
            for relationship in self.relationships
        ],
        "decision": self.export_decision(),
        "pending_movement": self._export_pending_movement(),
    }


def _export_creature(
    state: EncounterState,
    creature_ref: str,
) -> dict[str, object]:
    creature_state = state.creatures[creature_ref]
    creature = creature_state.creature
    movement_remaining = (
        creature_state.movement_remaining
        if creature_state.movement_remaining is not None
        else movement_budget_for(creature, state.definition.grid)
    )
    spellcasting = creature.spellcasting
    effective = state.effective_conditions_for(creature_ref)
    return {
        "creature_ref": creature_ref,
        "creature_id": creature_state.creature_id,
        "name": creature.name,
        "label": state._creature_label(creature_ref),
        "token_image": creature.token_image,
        "position": {
            "x": creature_state.position.x,
            "y": creature_state.position.y,
        },
        "health": creature.get_health(),
        "max_health": creature.get_max_health(),
        "temporary_hit_points": creature.temporary_hit_points,
        "statistics": {
            "creature_type": creature.statistics.creature_type,
            "type_tags": list(creature.statistics.type_tags),
            "alignment": list(creature.statistics.alignment),
            "challenge_rating": creature.statistics.challenge_rating,
            "saving_throw_bonuses": dict(creature.statistics.saving_throw_bonuses),
            "skill_bonuses": dict(creature.statistics.skill_bonuses),
            "senses": list(creature.statistics.senses),
            "effective_senses": {
                sense: distance
                for sense in ("blindsight", "darkvision", "truesight")
                if (distance := creature.sense_range(sense)) is not None
            },
            "passive_perception": creature.statistics.passive_perception,
            "languages": list(creature.statistics.languages),
        },
        "movement_remaining": movement_remaining,
        "movement_total": movement_budget_for(creature, state.definition.grid),
        "movement_remaining_feet": (
            state.definition.grid.feet_for_squares(movement_remaining)
        ),
        "movement_total_feet": creature.effective_speed_feet(),
        "action_available": creature_state.actions_remaining > 0,
        "actions_remaining": creature_state.actions_remaining,
        "attacks_remaining": creature_state.attacks_remaining,
        "attacks_per_attack_action": (
            creature.combat_profile.attacks_per_attack_action
        ),
        "bonus_action_available": creature_state.bonus_action_available,
        "reaction_available": creature_state.reaction_available,
        "conditions": [
            condition.condition.value
            for condition in state.conditions_for(creature_ref)
        ],
        "effective_conditions": [
            {
                "condition": condition.condition.value,
                "provider_ids": list(condition.provider_ids),
            }
            for condition in effective.conditions
        ],
        "traits": [
            {
                "trait": trait.trait.value,
                "provider_ids": list(trait.provider_ids),
            }
            for trait in effective.traits
        ],
        "suppressed_conditions": [
            {
                "condition": condition.condition.value,
                "provider_ids": list(condition.provider_ids),
                "reason": condition.reason,
            }
            for condition in effective.suppressed_conditions
        ],
        "condition_immunities": sorted(
            condition.value
            for condition in creature.condition_immunities()
        ),
        "spell_slots_max": (
            {str(level): slots for level, slots in spellcasting.spell_slots_max.items()}
            if spellcasting is not None
            else {}
        ),
        "spell_slots_remaining": (
            {
                str(level): slots
                for level, slots in spellcasting.spell_slots_remaining.items()
            }
            if spellcasting is not None
            else {}
        ),
        "team_id": state._creature_team_id(creature_ref),
        "controller": state._creature_controller(creature_ref),
        "is_alive": creature_state.is_alive,
    }


def export_pending_movement(self: EncounterState) -> dict[str, object] | None:
    movement = self.pending_movement
    if movement is None:
        return None
    return {
        "action_id": movement.action_id,
        "creature_ref": movement.creature_ref,
        "direction": movement.direction,
        "from": {
            "x": movement.from_position.x,
            "y": movement.from_position.y,
        },
        "to": {
            "x": movement.to_position.x,
            "y": movement.to_position.y,
        },
        "remaining_movement_after": movement.remaining_movement_after,
        "trigger_id": movement.trigger_id,
        "companion_destinations": {
            creature_ref: {"x": position.x, "y": position.y}
            for creature_ref, position in movement.companion_destinations.items()
        },
    }


def _condition_suffix(conditions: tuple[AppliedCondition, ...]) -> str:
    if not conditions:
        return ""
    labels = ", ".join(
        condition.condition.value.capitalize() for condition in conditions
    )
    return f" [{labels}]"


def _export_source(source: EffectSource) -> dict[str, object]:
    return {
        "kind": source.kind.value,
        "definition_id": source.definition_id,
        "applied_by_ref": source.applied_by_ref,
        "origin_id": source.origin_id,
    }


def _export_duration(duration: EffectDuration) -> dict[str, object]:
    if isinstance(duration, Indefinite):
        return {"kind": "indefinite"}
    if isinstance(duration, UntilTurnStart):
        return {
            "kind": "until_turn_start",
            "creature_ref": duration.creature_ref,
            "round_number": duration.round_number,
        }
    if isinstance(duration, UntilTurnEnd):
        return {
            "kind": "until_turn_end",
            "creature_ref": duration.creature_ref,
            "round_number": duration.round_number,
        }
    if isinstance(duration, Rounds):
        return {"kind": "rounds", "count": duration.count}
    if isinstance(duration, WhileParentExists):
        return {"kind": "while_parent_exists"}
    raise TypeError(f"Unsupported effect duration: {duration!r}")
