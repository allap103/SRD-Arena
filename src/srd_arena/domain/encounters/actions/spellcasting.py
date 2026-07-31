from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...effects import serialize_effects
from ..models import EncounterProgress
from ...spells.resolution import (
    SpellActionContext,
    resolve_spell_action as _resolve_spell_action_impl,
)
from ...spells.rules import parse_spell_action_value

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
    block_reason = self._spell_cast_block_reason(spellcasting, spell, cost)
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
    targets = self._spell_area_targets(actor, spell, target_ref=target_ref, aim_point=aim_point)
    target = (
        self._spell_target_context(actor, target_ref)
        if target_ref is not None
        else targets[0]
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

    self._spend_spell_resources(spellcasting, spell, cost)
    progress.messages.extend(result.messages)
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
                    spellcasting.spell_slots_remaining.get(spell.level, 0)
                    if spell.level > 0
                    else None
                ),
                "save_detail": result.details.get("save_detail"),
                "save_details": result.details.get("save_details"),
                "damage_roll_detail": result.details.get("damage_roll_detail"),
                "damage_roll_details": result.details.get("damage_roll_details"),
                "effects": serialize_effects(result.effects),
                "success": result.details.get("success", False),
            },
        )
    )
