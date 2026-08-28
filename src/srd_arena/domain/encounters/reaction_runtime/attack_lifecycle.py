"""Apply lifecycle consequences shared by resolved reaction attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def resolve_attack_lifecycle(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    damage: int,
    progress: EncounterProgress,
) -> None:
    """Publish attack/damage triggers and resolve concentration damage.

    A damaging attack publishes the attack itself plus both damage-facing
    lifecycle events before checking the target's concentration.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
    >>> with patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.attack_lifecycle."
    ...     "resolve_spell_lifecycle_event"
    ... ) as lifecycle, patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.attack_lifecycle."
    ...     "resolve_concentration_damage"
    ... ) as concentration:
    ...     resolve_attack_lifecycle(
    ...         SimpleNamespace(),
    ...         attacker_ref="guard",
    ...         target_ref="hero",
    ...         damage=7,
    ...         progress=EncounterProgress(),
    ...     )
    >>> [call.args[1] for call in lifecycle.call_args_list]
    ['target_makes_attack', 'target_damaged', 'target_deals_damage']
    >>> concentration.call_args.args[2]
    7
    """

    resolve_spell_lifecycle_event(
        state,
        "target_makes_attack",
        actor_ref=attacker_ref,
        target_ref=target_ref,
        progress=progress,
    )
    if damage > 0:
        resolve_spell_lifecycle_event(
            state,
            "target_damaged",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
        resolve_spell_lifecycle_event(
            state,
            "target_deals_damage",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
    resolve_concentration_damage(state, target_ref, damage, progress)
