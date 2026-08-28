"""Convert encounter values into immutable event payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.conditions import AppliedCondition
from ..effects.rule_effects import serialize_runtime_rule_effect
from ..effects.runtime import (
    EffectDuration,
    EffectSource,
    Indefinite,
    Rounds,
    UntilTurnEnd,
    UntilTurnStart,
    WhileParentExists,
)
from .models import ActionCost, EncounterAction

if TYPE_CHECKING:
    from .encounter import EncounterState


def export_decision(self: EncounterState) -> dict[str, object]:
    """Convert a pending decision and its invocation stack into immutable data.

    >>> from types import SimpleNamespace
    >>> frame = SimpleNamespace(
    ...     id="turn-1", creature_ref="hero", kind="turn", reason="active",
    ...     can_pass=False, parent_frame_id=None, parent_action_id=None,
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: frame,
    ...     pending_movement=None,
    ... )
    >>> payload = export_decision(state)
    >>> (payload["frame_id"], payload["creature_ref"], payload["kind"])
    ('turn-1', 'hero', 'turn')
    """

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
    """Snapshot mutable encounter state into client-safe primitive values.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> frame = SimpleNamespace(creature_ref="hero")
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: frame,
    ...     encounter_id="demo",
    ...     definition=SimpleNamespace(grid=SimpleNamespace(width=8, height=6)),
    ...     round_number=2, turn_index=0, initiative_order=["hero"],
    ...     initiative_entries=[], creatures={"hero": object()},
    ...     conditions=[], ongoing_effects=[], relationships=[],
    ...     _creature_controller=lambda ref: "external",
    ...     export_decision=lambda: {"frame_id": "turn-1"},
    ...     _export_pending_movement=lambda: None,
    ... )
    >>> with patch(
    ...     "srd_arena.domain.encounters.serialization._export_creature",
    ...     return_value={"name": "Hero"},
    ... ):
    ...     payload = export_state(state)
    >>> (payload["encounter_id"], payload["grid"], payload["creatures"])
    ('demo', {'width': 8, 'height': 6}, {'hero': {'name': 'Hero'}})
    """

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
                "polarity": effect.polarity.value,
                "target_refs": list(effect.target_refs),
                "duration": _export_duration(effect.duration),
                "root_id": effect.identity.root_id,
                "parent_id": effect.identity.parent_id,
                "parameters": dict(effect.parameters),
                "dispellable": effect.dispellable,
                "tags": sorted(tag.value for tag in effect.tags),
                "rule_effects": [
                    serialize_runtime_rule_effect(rule_effect)
                    for rule_effect in effect.rule_effects
                ],
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
    movement = state.combat_rules.movement_budget(state, creature_ref)
    armor_class = state.combat_rules.effective_armor_class(state, creature_ref)
    movement_remaining = (
        creature_state.movement_remaining
        if creature_state.movement_remaining is not None
        else movement.budget
    )
    spellcasting = creature.spellcasting
    effective = state.effective_conditions_for(creature_ref)
    action_available = state.combat_rules.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            "Action",
            "action",
            creature_ref=creature_ref,
            cost=ActionCost(action=1),
        ),
    ).allowed
    bonus_action_available = state.combat_rules.action_compatibility(
        state,
        creature_ref,
        EncounterAction(
            "Bonus Action",
            "bonus_action",
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
        "armor_class": armor_class.value,
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
        "movement_total": movement.budget,
        "movement_spent_this_turn": creature_state.movement_spent_this_turn,
        "movement_remaining_feet": (
            state.definition.grid.feet_for_squares(movement_remaining)
        ),
        "movement_total_feet": movement.speed.value,
        "action_available": action_available,
        "actions_remaining": creature_state.actions_remaining,
        "action_used_this_turn": creature_state.action_used_this_turn,
        "attacks_remaining": creature_state.attacks_remaining,
        "attack_action_base_attacks": creature_state.attack_action_base_attacks,
        "attack_action_attacks_used": creature_state.attack_action_attacks_used,
        "attacks_per_attack_action": attacks_per_attack_action,
        "bonus_action_available": bonus_action_available,
        "bonus_action_used_this_turn": creature_state.bonus_action_used_this_turn,
        "reaction_available": reaction_available,
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
            condition.value for condition in creature.condition_immunities()
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
    """Serialize an in-progress movement path and its remaining budget.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.encounters.models import PendingMovement
    >>> from srd_arena.domain.geometry import MovementBudget, MovementCost, Position
    >>> movement = PendingMovement(
    ...     "move-1", "hero", "right", Position(0, 0), Position(1, 0),
    ...     MovementBudget(5), MovementCost(1), "trigger-1",
    ... )
    >>> payload = export_pending_movement(SimpleNamespace(pending_movement=movement))
    >>> (payload["to"], int(payload["remaining_movement_after"]))
    ({'x': 1, 'y': 0}, 5)
    """

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
        "movement_cost": movement.movement_cost,
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
