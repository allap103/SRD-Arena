"""Apply encounter consequences after source-neutral spell resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects import serialize_effects
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    SpellResolutionDetails,
)

from ...effect_lifecycle.concentration import resolve_concentration_damage
from ...effect_lifecycle.lifecycle_events import resolve_spell_lifecycle_event
from ...encounter_models.resolution import EncounterProgress
from ...state_runtime import apply_encounter_effects, create_event

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Spellcasting
    from srd_arena.domain.spells.definitions import Spell

    from ...encounter import EncounterState


def apply_spell_result(
    state: EncounterState,
    *,
    spellcasting: Spellcasting,
    spell: Spell,
    cast_level: int | None,
    creature_ref: str,
    action_id: str,
    result: ActionResolutionResult,
    progress: EncounterProgress,
) -> None:
    """Publish resolved effects and record the completed cast.

    The encounter-facing event preserves spell metadata alongside the generic
    capability result so frontends do not need to inspect domain objects.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.effects.results import (
    ...     ActionResolutionResult, SpellResolutionDetails,
    ... )
    >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
    >>> from srd_arena.domain.spells import Spell
    >>> state = SimpleNamespace(event_sequence=1)
    >>> details = SpellResolutionDetails(
    ...     "dummy", "Dummy", (("dummy", "Dummy"),), (), None, 0, 0
    ... )
    >>> result = ActionResolutionResult(
    ...     "fire-bolt", "Fire Bolt", [], [], details=details
    ... )
    >>> progress = EncounterProgress()
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.spell_runtime.aftermath."
    ...     "apply_encounter_effects", return_value=[]
    ... ):
    ...     apply_spell_result(
    ...         state,
    ...         spellcasting=SimpleNamespace(spell_slots_remaining={}),
    ...         spell=Spell("fire-bolt", "Fire Bolt", None, 0),
    ...         cast_level=None,
    ...         creature_ref="mage",
    ...         action_id="cast",
    ...         result=result,
    ...         progress=progress,
    ...     )
    >>> (progress.events[0].type, progress.events[0].data["spell_id"])
    ('spell_cast', 'fire-bolt')
    """

    details = result.details
    if not isinstance(details, SpellResolutionDetails):
        raise TypeError("Spell resolution returned non-spell details.")
    progress.messages.extend(result.messages)
    _apply_damage_lifecycle(
        state,
        result,
        creature_ref=creature_ref,
        progress=progress,
    )
    progress.messages.extend(
        apply_encounter_effects(state, result.effects, origin_id=action_id)
    )
    progress.events.append(
        create_event(
            state,
            "spell_cast",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "spell",
                "spell_id": result.definition_id,
                "spell_name": result.definition_name,
                "spell_level": details.spell_level,
                "target_ref": details.target_ref,
                "target_label": details.target_label,
                "target_refs": [ref for ref, _label in details.targets],
                "target_labels": [label for _ref, label in details.targets],
                "area": details.area,
                "slot_level": details.slot_level,
                "spell_slots_remaining": (
                    spellcasting.spell_slots_remaining.get(
                        cast_level if cast_level is not None else spell.level,
                        0,
                    )
                    if spell.level > 0
                    else None
                ),
                "save_detail": _first(details.save_details),
                "save_details": list(details.save_details),
                "attack_roll_detail": _first(details.attack_roll_details),
                "attack_roll_details": list(details.attack_roll_details),
                "damage_roll_detail": _first(details.damage_roll_details),
                "damage_roll_details": list(details.damage_roll_details),
                "healing_roll_detail": _first(details.healing_roll_details),
                "healing_roll_details": list(details.healing_roll_details),
                "temporary_hit_point_detail": _first(
                    details.temporary_hit_point_details
                ),
                "temporary_hit_point_details": list(
                    details.temporary_hit_point_details
                ),
                "effects": serialize_effects(result.effects),
                "success": details.success,
            },
        )
    )


def _apply_damage_lifecycle(
    state: EncounterState,
    result: ActionResolutionResult,
    *,
    creature_ref: str,
    progress: EncounterProgress,
) -> None:
    details = result.details
    if not isinstance(details, SpellResolutionDetails):
        return
    for damage in details.damage_applications:
        if damage.amount > 0:
            resolve_spell_lifecycle_event(
                state,
                "target_damaged",
                actor_ref=creature_ref,
                target_ref=damage.target_ref,
                progress=progress,
            )
            resolve_spell_lifecycle_event(
                state,
                "target_deals_damage",
                actor_ref=creature_ref,
                target_ref=damage.target_ref,
                progress=progress,
            )
        resolve_concentration_damage(
            state,
            damage.target_ref,
            damage.amount,
            progress,
        )


def _first(
    details: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    return details[0] if details else None
