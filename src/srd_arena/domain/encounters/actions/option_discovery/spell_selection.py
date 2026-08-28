"""Advertise the staged add, remove, confirm, and cancel actions for spell targets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....spells.rules import parse_spell_action_value, spell_chooses_area_targets
from ...encounter_models.actions import EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_target_selection_actions(
    state: EncounterState,
    creature_ref: str,
) -> list[EncounterAction]:
    """Build actions that mutate or confirm the current staged target selection.

    >>> from types import SimpleNamespace
    >>> spell_target_selection_actions(
    ...     SimpleNamespace(pending_spell_cast=None), "mage"
    ... )
    []
    """

    pending = state.pending_spell_cast
    if pending is None:
        return []
    actor = state.creatures[creature_ref].creature
    spell = (
        next(
            candidate
            for candidate in actor.spellcasting.learned_spells
            if candidate.id == pending.spell_id
        )
        if actor.spellcasting is not None
        else None
    )
    if spell is None:
        return []
    actions: list[EncounterAction] = []
    _spell_id, _target_ref, aim_point = parse_spell_action_value(
        str(pending.action.value)
    )
    candidates = (
        state._spell_area_targets(actor, spell, aim_point=aim_point)
        if spell_chooses_area_targets(spell)
        else tuple(state._spell_action_targets(actor, spell))
    )
    if pending.resource_pool_total is not None:
        for target in candidates:
            limit = pending.resource_allocation_limits.get(target.target_ref)
            if limit is None:
                continue
            current = pending.resource_allocations.get(target.target_ref, 0)
            actions.append(
                EncounterAction(
                    f"Allocate healing to {target.target_label}",
                    "set_spell_resource_allocation",
                    f"{target.target_ref}~{current}",
                    id=(
                        f"{creature_ref}-spell-allocation-"
                        f"{target.target_ref.replace(':', '-')}"
                    ),
                    creature_ref=creature_ref,
                    source_trigger_id=pending.spell_id,
                )
            )
        allocated = sum(pending.resource_allocations.values())
        if allocated > 0:
            actions.append(
                EncounterAction(
                    f"Cast {spell.name} ({allocated}/{pending.resource_pool_total} HP)",
                    "confirm_spell_targets",
                    id=f"{creature_ref}-confirm-{spell.id}",
                    creature_ref=creature_ref,
                    cost=pending.action.cost,
                )
            )
        actions.append(
            EncounterAction(
                f"Cancel {spell.name}",
                "cancel_spell_targets",
                id=f"{creature_ref}-cancel-{spell.id}",
                creature_ref=creature_ref,
            )
        )
        return actions
    for target in candidates:
        if pending.repeat_target_allocations:
            selected_count = pending.selected_target_refs.count(target.target_ref)
            if selected_count:
                actions.append(
                    EncounterAction(
                        f"Remove {target.target_label} ({selected_count})",
                        "toggle_spell_target",
                        target.target_ref,
                        id=(
                            f"{creature_ref}-spell-target-"
                            f"{target.target_ref.replace(':', '-')}-remove"
                        ),
                        creature_ref=creature_ref,
                        source_trigger_id=pending.spell_id,
                    )
                )
            if len(pending.selected_target_refs) < pending.maximum_targets:
                actions.append(
                    EncounterAction(
                        f"Add {target.target_label} ({selected_count + 1})",
                        "toggle_spell_target",
                        target.target_ref,
                        id=(
                            f"{creature_ref}-spell-target-"
                            f"{target.target_ref.replace(':', '-')}-add"
                        ),
                        creature_ref=creature_ref,
                        source_trigger_id=pending.spell_id,
                    )
                )
            continue
        selected = target.target_ref in pending.selected_target_refs
        if (
            not selected
            and len(pending.selected_target_refs) >= pending.maximum_targets
        ):
            continue
        actions.append(
            EncounterAction(
                ("Remove " if selected else "Add ") + target.target_label,
                "toggle_spell_target",
                target.target_ref,
                id=(
                    f"{creature_ref}-spell-target-{target.target_ref.replace(':', '-')}"
                ),
                creature_ref=creature_ref,
                source_trigger_id=pending.spell_id,
            )
        )
    can_confirm = bool(pending.selected_target_refs) and (
        not pending.require_full_target_count
        or len(pending.selected_target_refs) == pending.maximum_targets
    )
    if can_confirm:
        actions.append(
            EncounterAction(
                f"Cast {spell.name} ({len(pending.selected_target_refs)}/"
                f"{pending.maximum_targets} targets)",
                "confirm_spell_targets",
                id=f"{creature_ref}-confirm-{spell.id}",
                creature_ref=creature_ref,
                cost=pending.action.cost,
            )
        )
    actions.append(
        EncounterAction(
            f"Cancel {spell.name}",
            "cancel_spell_targets",
            id=f"{creature_ref}-cancel-{spell.id}",
            creature_ref=creature_ref,
        )
    )
    return [
        action
        for action in actions
        if state.combat_rules.action_eligibility(
            state,
            creature_ref,
            action,
        ).allowed
    ]
