"""Apply lifecycle consequences shared by resolved reaction attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..models import EncounterProgress


def resolve_attack_lifecycle(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    damage: int,
    progress: EncounterProgress,
) -> None:
    """Publish attack/damage triggers and resolve concentration damage."""

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
