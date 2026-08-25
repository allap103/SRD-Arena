"""Build actor-relative encounter action candidates in presentation order."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...models import CreatureRef, EncounterAction
from ..eligibility import action_eligibility
from .attacks import attack_action_candidates
from .movement_candidates import movement_action_candidates
from .special import special_action_candidates
from .stat_blocks import stat_block_action_candidates

if TYPE_CHECKING:
    from ...encounter import EncounterState


def available_creature_actions(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    include_attack_alternatives: bool = False,
) -> list[EncounterAction]:
    """Return candidates that pass every current eligibility rule."""

    return [
        action
        for action in creature_action_candidates(
            state,
            creature_ref,
            include_attack_alternatives=include_attack_alternatives,
        )
        if action_eligibility(state, creature_ref, action).allowed
    ]


def creature_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    include_attack_alternatives: bool = False,
) -> list[EncounterAction]:
    """Describe every generally available action before eligibility filtering."""

    # This order is also the stable presentation order used by frontends.
    actions: list[EncounterAction] = []
    actions.extend(movement_action_candidates(state, creature_ref))
    actions.extend(
        attack_action_candidates(state, creature_ref, _stat_block_display_name)
    )
    actions.extend(
        stat_block_action_candidates(state, creature_ref, _stat_block_display_name)
    )
    actions.extend(special_action_candidates(state, creature_ref))
    return actions


def _stat_block_display_name(creature, name: str) -> str:
    return next(
        (
            declaration.display_name
            for declaration in creature.declared_stat_block_actions
            if declaration.name == name
        ),
        name,
    )
