from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...effects import serialize_effects
from ...effects.runtime import OngoingEffectKind
from ...geometry import build_radius_area
from ..models import EncounterProgress
from ...spells.resolution import (
    SpellActionContext,
    resolve_spell_action as _resolve_spell_action_impl,
)
from ...spells.rules import parse_spell_action_value
from ...spells.rules import parse_spell_action_targets
from ...spells.rules import parse_spell_action_condition
from ...spells.rules import parse_spell_action_damage_type
from ...spells.rules import parse_spell_action_ability
from ...spells.rules import parse_spell_action_slot
from ...spells.rules import parse_spell_healing_allocations
from ..ongoing_effects import (
    has_condition_save_advantage,
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def resolve_spell_action(
    self: EncounterState,
    actor: Creature,
    spell_value: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = self.current_decision().creature_ref
    spellcasting = actor.spellcasting
    if spellcasting is None:
        progress.messages.append(("system", "You cannot cast spells."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "spell", "success": False},
            )
        )
        return
    spell_id, target_ref, aim_point = parse_spell_action_value(spell_value)
    selected_target_refs = parse_spell_action_targets(spell_value)
    cast_level = parse_spell_action_slot(spell_value)
    spell = next((candidate for candidate in spellcasting.learned_spells if candidate.id == spell_id), None)
    if spell is None:
        progress.messages.append(("system", "That spell is not available."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "spell", "spell_id": spell_id, "success": False},
            )
        )
        return
    cost = self._spell_action_cost(spell)
    block_reason: str | None
    if cast_level is not None and (
        spell.level == 0 or cast_level <= spell.level or cast_level > 9
    ):
        block_reason = "That spell slot level is not available for this spell."
    else:
        block_reason = self._spell_cast_block_reason(
            spellcasting, spell, cost, cast_level
        )
    if block_reason is not None:
        progress.messages.append(("system", block_reason))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "spell", "spell_id": spell.id, "success": False},
            )
        )
        return
    area = self._spell_area(actor, spell, target_ref=target_ref, aim_point=aim_point)
    targets = (
        tuple(
            target
            for selected_ref in selected_target_refs
            if (target := self._spell_target_context(actor, selected_ref))
            is not None
        )
        if selected_target_refs
        else self._spell_area_targets(
            actor,
            spell,
            target_ref=target_ref,
            aim_point=aim_point,
        )
    )
    target = (
        targets[0]
        if targets
        else None
    )
    if target is None or not targets:
        progress.messages.append(("system", "That target is not available."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "spell", "spell_id": spell.id, "success": False},
            )
        )
        return
    result = _resolve_spell_action_impl(
        SpellActionContext(
            creature=actor,
            spell=spell,
            target=target,
            current_round=self.round_number,
            targets=targets,
            area=area,
            source_ref=creature_ref,
            roller=_roll_die,
            selected_condition=parse_spell_action_condition(spell_value),
            selected_damage_type=parse_spell_action_damage_type(spell_value),
            selected_ability=parse_spell_action_ability(spell_value),
            attack_roll_modes=(
                {
                    candidate.target_ref: self._attack_roll_mode_for(
                        creature_ref,
                        candidate.target_ref,
                        spell.capability.attack_mode,
                        self._creature_position(creature_ref),
                        tuple(
                            state.position
                            for opponent_ref, state in self.creatures.items()
                            if state.is_alive
                            and self._creatures_are_opponents(
                                creature_ref, opponent_ref
                            )
                        ),
                    )
                    for candidate in targets
                }
                if spell.capability is not None
                and spell.capability.resolution == "spell_attack"
                and spell.capability.attack_mode is not None
                else {}
            ),
            automatic_critical_providers={
                candidate.target_ref: self._automatic_critical_provider_ids_for(
                    creature_ref, candidate.target_ref
                )
                for candidate in targets
            },
            cast_level=cast_level,
            save_roll_modes=(
                {
                    candidate.target_ref: "advantage"
                    for candidate in targets
                    if (
                        spell.capability is not None
                        and has_condition_save_advantage(
                            self,
                            candidate.target_ref,
                            spell.capability.conditions,
                        )
                    )
                    or (
                        spell.capability.save_advantage_against_opponents
                        and self._creatures_are_opponents(
                            creature_ref, candidate.target_ref
                        )
                    )
                }
                if spell.capability is not None
                and (
                    spell.capability.save_advantage_against_opponents
                    or spell.capability.conditions
                )
                else {}
            ),
            area_targets_around=lambda center_ref, radius_feet: tuple(
                self._targets_in_area(
                    actor,
                    build_radius_area(
                        self._creature_position(center_ref),
                        int(
                            self.definition.grid.distance_from_feet(
                                radius_feet,
                                minimum=1,
                            )
                        ),
                        self.definition.grid,
                    ),
                )
            ),
            healing_allocations=parse_spell_healing_allocations(spell_value),
        )
    )
    if result is None:
        progress.messages.append(("system", f"{spell.name} is not implemented yet."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "spell", "spell_id": spell.id, "success": False},
            )
        )
        return

    self._spend_spell_resources(spellcasting, spell, cost, cast_level)
    progress.messages.extend(result.messages)
    damage_details = result.details.get("damage_roll_details")
    if isinstance(damage_details, list):
        for detail in damage_details:
            if not isinstance(detail, dict):
                continue
            damaged_ref = detail.get("target_ref")
            applied_damage = detail.get("applied_damage")
            if isinstance(damaged_ref, str) and isinstance(applied_damage, int):
                if applied_damage > 0:
                    resolve_spell_lifecycle_event(
                        self,
                        "target_damaged",
                        actor_ref=creature_ref,
                        target_ref=damaged_ref,
                        progress=progress,
                    )
                    resolve_spell_lifecycle_event(
                        self,
                        "target_deals_damage",
                        actor_ref=creature_ref,
                        target_ref=damaged_ref,
                        progress=progress,
                    )
                resolve_concentration_damage(
                    self,
                    damaged_ref,
                    applied_damage,
                    progress,
                )
    resolve_spell_lifecycle_event(
        self,
        "target_casts_spell",
        actor_ref=creature_ref,
        progress=progress,
    )
    if any(
        effect.kind == "start_ongoing_effect"
        and effect.data.get("effect_kind") == "concentration"
        for effect in result.effects
    ):
        for existing in self.ongoing_effects:
            if (
                existing.kind is OngoingEffectKind.CONCENTRATION
                and existing.identity.source.applied_by_ref == creature_ref
            ):
                effect_label = existing.parameters.get("effect_label")
                if not isinstance(effect_label, str):
                    effect_label = existing.identity.source.definition_id.replace(
                        "_", " "
                    ).title()
                progress.messages.append(
                    (
                        "system",
                        f"{actor.name} drops concentration on {effect_label}.",
                    )
                )
    progress.messages.extend(
        self._apply_effects(result.effects, origin_id=action_id)
    )
    progress.events.append(
        self._event(
            "spell_cast",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "spell",
                "spell_id": result.capability_id,
                "spell_name": result.capability_name,
                "spell_level": result.details.get("spell_level", spell.level),
                "target_ref": result.details.get("target_ref", target_ref),
                "target_label": result.details.get("target_label", target.target_label),
                "target_refs": result.details.get("target_refs"),
                "target_labels": result.details.get("target_labels"),
                "area": result.details.get("area"),
                "slot_level": result.details.get("slot_level", spell.level),
                "spell_slots_remaining": (
                    spellcasting.spell_slots_remaining.get(
                        cast_level if cast_level is not None else spell.level, 0
                    )
                    if spell.level > 0
                    else None
                ),
                "save_detail": result.details.get("save_detail"),
                "save_details": result.details.get("save_details"),
                "attack_roll_detail": result.details.get("attack_roll_detail"),
                "attack_roll_details": result.details.get("attack_roll_details"),
                "damage_roll_detail": result.details.get("damage_roll_detail"),
                "damage_roll_details": result.details.get("damage_roll_details"),
                "healing_roll_detail": result.details.get("healing_roll_detail"),
                "healing_roll_details": result.details.get("healing_roll_details"),
                "temporary_hit_point_detail": result.details.get(
                    "temporary_hit_point_detail"
                ),
                "temporary_hit_point_details": result.details.get(
                    "temporary_hit_point_details"
                ),
                "effects": serialize_effects(result.effects),
                "success": result.details.get("success", False),
            },
        )
    )
