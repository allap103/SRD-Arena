"""Apply damage-derived changes to a target's maximum Hit Points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects import EffectResult, MaximumHitPointAdjustment

from ..effect_lifecycle.application import start_ongoing_effect
from ..encounter_models.resolution import EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState


def apply_damage_derived_maximum_hit_point_reduction(
    state: EncounterState,
    *,
    source_ref: str,
    target_ref: str,
    damage_taken: int,
    progress: EncounterProgress,
    origin_id: str,
    definition_id: str,
) -> int:
    """Persist a maximum-HP reduction equal to damage the target actually took."""

    if damage_taken <= 0:
        return 0
    source = state.creatures[source_ref].creature
    target = state.creatures[target_ref].creature
    start_ongoing_effect(
        state,
        EffectResult(
            kind="start_ongoing_effect",
            target_ref=target_ref,
            data={
                "source_ref": source_ref,
                "source_label": source.name,
                # Each instantaneous drain changes the maximum independently.
                # A unique definition ID therefore preserves cumulative drains.
                "definition_id": f"{definition_id}:{origin_id}",
                "effect_kind": "generic",
                "source_kind": "action",
                "polarity": "harmful",
                "dispellable": False,
            },
            rule_effects=(MaximumHitPointAdjustment(-damage_taken),),
            effect_label=definition_id,
        ),
        f"{origin_id}:maximum-hit-point-reduction",
    )
    progress.messages.append(
        (
            "system",
            f"{target.name}'s Hit Point maximum decreases by {damage_taken}.",
        )
    )
    return damage_taken
