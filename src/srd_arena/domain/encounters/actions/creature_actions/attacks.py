"""Provide attacks support for the creature actions package."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ....creatures import Creature
from ...models import ActionCost, CreatureRef, EncounterAction
from ..attack_resolution import attack_sources
from ..stat_block import executable_multiattack_slot_plans

if TYPE_CHECKING:
    from ...encounter import EncounterState


def attack_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
    display_name: Callable[[Creature, str], str],
) -> list[EncounterAction]:
    """Handle attack action candidates."""

    actor = state.creatures[creature_ref]
    actions: list[EncounterAction] = []

    multiattack_plans = executable_multiattack_slot_plans(actor.creature)
    for plan_index, slots in enumerate(multiattack_plans):
        plan_summary = [
            "/".join(invocation.name for invocation in slot.options) for slot in slots
        ]
        label = (
            "Multiattack"
            if len(multiattack_plans) == 1
            else f"Multiattack ({', '.join(plan_summary)})"
        )
        actions.append(
            EncounterAction(
                label,
                "multiattack",
                (None if len(multiattack_plans) == 1 else str(plan_index)),
                id=(
                    f"{creature_ref}-multiattack"
                    if len(multiattack_plans) == 1
                    else f"{creature_ref}-multiattack-{plan_index}"
                ),
                creature_ref=creature_ref,
                cost=ActionCost(action=1),
            )
        )

    opponent_refs = [
        target_ref
        for target_ref in state._living_creature_refs()
        if state._creatures_are_opponents(creature_ref, target_ref)
    ]
    attack_target_refs: list[str | None] = (
        list(opponent_refs) if opponent_refs else [None]
    )
    for target_ref in attack_target_refs:
        available_sources = attack_sources(actor.creature, state.item_templates)
        if actor.pending_multiattack:
            option_names = {
                invocation.name for invocation in actor.pending_multiattack[0].options
            }
            available_sources = [
                source for source in available_sources if source.name in option_names
            ]
        for source in available_sources:
            for attack_type in source.attack_modes:
                source_slug = source.name.lower().replace(" ", "-")
                target_slug = (
                    target_ref.replace(":", "-")
                    if isinstance(target_ref, str)
                    else "no-target"
                )
                actions.append(
                    EncounterAction(
                        display_name(actor.creature, source.name),
                        "attack",
                        target_ref,
                        id=(
                            f"{creature_ref}-attack-{source_slug}-{attack_type}-"
                            f"{target_slug}"
                        ),
                        creature_ref=creature_ref,
                        cost=ActionCost(
                            action=1 if actor.attacks_remaining == 0 else 0
                        ),
                        source_trigger_id=(
                            source.name if actor.pending_multiattack else None
                        ),
                        preferred_attack_type=attack_type,
                        preferred_attack_name=source.name,
                    )
                )
        actions.append(
            EncounterAction(
                "Grapple",
                "grapple",
                target_ref,
                id=(
                    f"{creature_ref}-grapple-"
                    f"{target_ref.replace(':', '-') if isinstance(target_ref, str) else 'no-target'}"
                ),
                creature_ref=creature_ref,
                cost=ActionCost(action=1 if actor.attacks_remaining == 0 else 0),
            )
        )
    return actions
