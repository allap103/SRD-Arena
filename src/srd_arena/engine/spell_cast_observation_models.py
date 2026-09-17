"""Detached configuration choices for assembling a spell cast in an adapter."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpellCastOptions:
    """Public target grammar for a complete cast, independent of a local draft."""

    target_refs: tuple[str, ...]
    initial_target_refs: tuple[str, ...]
    maximum_targets: int
    repeat_targets: bool
    require_full_count: bool
    select_targets: bool
    resource_pool: int | None = None
    resource_limits: tuple[tuple[str, int], ...] = ()
    maximum_is_area_count: bool = False
