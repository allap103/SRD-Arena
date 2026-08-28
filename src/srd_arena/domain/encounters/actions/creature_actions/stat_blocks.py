"""Discover executable actions authored in a creature's stat block."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ....creatures import (
    AutomaticActionDefinition,
    Creature,
    SavingThrowActionDefinition,
)
from ...encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)

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
        if not isinstance(
            definition,
            (AutomaticActionDefinition, SavingThrowActionDefinition),
        ):
            continue
        targets: list[str | tuple[float, float] | None] = (
            [creature_ref]
            if definition.target.kind == "self"
            else [
                (
                    actor.position.x + 1.5,
                    actor.position.y + 0.5,
                )
            ]
            if definition.target.kind == "area"
            else [
                target_ref
                for target_ref in state._living_creature_refs()
                if state._creatures_are_opponents(creature_ref, target_ref)
            ]
            if definition.target.kind == "creature"
            else []
        )
        if definition.target.kind == "creature" and not targets:
            targets = [None]
        for target in targets:
            source_slug = definition.name.lower().replace(" ", "-")
            target_slug = (
                target.replace(":", "-")
                if isinstance(target, str)
                else "aim"
                if isinstance(target, tuple)
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
                    cost=ActionCost(action=1),
                )
            )
    return actions
