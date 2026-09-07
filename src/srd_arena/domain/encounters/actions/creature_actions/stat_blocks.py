"""Discover executable actions authored in a creature's stat block."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from srd_arena.domain.creatures import (
    AutomaticActionDefinition,
    Creature,
    SavingThrowActionDefinition,
    StandardActionGrantDefinition,
)

from ...encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)
from ...participants import creatures_are_opponents
from ...state_runtime import living_creature_refs

if TYPE_CHECKING:
    from ...encounter import EncounterState


def stat_block_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
    display_name: Callable[[Creature, str], str],
) -> list[EncounterAction]:
    """Build actor-relative candidates from all supported stat-block sections.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(
    ...     creature=SimpleNamespace(stat_block_actions={}),
    ...     position=SimpleNamespace(x=0, y=0),
    ... )
    >>> state = SimpleNamespace(creatures={"hero": actor})
    >>> stat_block_action_candidates(
    ...     state, "hero", lambda creature, name: name
    ... )
    []
    """

    actor = state.creatures[creature_ref]
    actions: list[EncounterAction] = []
    for definition in actor.creature.stat_block_actions.values():
        pending_names = (
            {invocation.name for invocation in actor.pending_multiattack[0].options}
            if actor.pending_multiattack
            else None
        )
        if pending_names is not None and definition.name not in pending_names:
            continue
        if isinstance(definition, StandardActionGrantDefinition):
            cost = (
                ActionCost(bonus_action=1)
                if definition.economy == "bonus_action"
                else ActionCost(action=1)
            )
            source_slug = definition.name.lower().replace(" ", "-")
            actions.extend(
                EncounterAction(
                    f"{display_name(actor.creature, definition.name)} — "
                    f"{granted_action.replace('_', ' ').title()}",
                    granted_action,
                    id=(
                        f"{creature_ref}-stat-block-{source_slug}-"
                        f"{granted_action.replace('_', '-')}"
                    ),
                    creature_ref=creature_ref,
                    preferred_attack_name=definition.name,
                    cost=cost,
                )
                for granted_action in definition.actions
            )
            continue
        if not isinstance(
            definition,
            (AutomaticActionDefinition, SavingThrowActionDefinition),
        ):
            continue
        targets: list[str | tuple[float, float] | None] = (
            [creature_ref]
            if definition.target.kind == "self"
            else [None]
            if definition.target.kind == "area"
            else [
                target_ref
                for target_ref in living_creature_refs(state)
                if creatures_are_opponents(state, creature_ref, target_ref)
            ]
            if definition.target.kind == "creature"
            else []
        )
        if definition.target.kind == "creature" and not targets:
            targets = [None]
        for target in targets:
            source_slug = definition.name.lower().replace(" ", "-")
            target_slug = (
                "aim"
                if definition.target.kind == "area"
                else target.replace(":", "-")
                if isinstance(target, str)
                else "no-target"
            )
            actions.append(
                EncounterAction(
                    display_name(actor.creature, definition.name),
                    "stat_block",
                    target,
                    id=f"{creature_ref}-stat-block-{source_slug}-{target_slug}",
                    creature_ref=creature_ref,
                    preferred_attack_name=definition.name,
                    aim_committed=definition.target.kind != "area",
                    cost=ActionCost(action=0 if pending_names is not None else 1),
                )
            )
    return actions
