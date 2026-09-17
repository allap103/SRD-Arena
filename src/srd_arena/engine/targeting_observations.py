"""Engine snapshots contain no frontend spell drafts."""

from srd_arena.domain.encounters.encounter import EncounterState

from .observation_models import TargetingObservation


def observe_targeting(state: EncounterState) -> TargetingObservation | None:
    """Retain the legacy view field as null; draft state belongs to adapters."""
    return None


def observe_player_targeting(
    state: EncounterState,
    allied_refs: frozenset[str],
) -> TargetingObservation | None:
    """Gameplay observations never contain a client's unsubmitted draft."""
    return None
