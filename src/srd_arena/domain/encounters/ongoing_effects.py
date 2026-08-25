"""Stable facade for encounter-scoped ongoing-effect lifecycle services.

The implementation is organized by concern under :mod:`effect_lifecycle`.
This module intentionally retains the established import and dice-patching
surface used by the encounter runtime and its tests.
"""

from __future__ import annotations


def _roll_die(sides: int) -> int:
    """Roll through the encounter module's runtime-patchable dice seam."""

    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


from .effect_lifecycle.application import (  # noqa: E402
    _required_string,
    start_ongoing_effect,
)
from .effect_lifecycle.concentration import (  # noqa: E402
    end_concentration,
    resolve_concentration_damage,
)
from .effect_lifecycle.lifecycle_events import (  # noqa: E402
    resolve_spell_lifecycle_event,
)
from .effect_lifecycle.removal import (  # noqa: E402
    _remove_damage_resistances,
    _remove_effect_target,
    _remove_effect_tree,
    _remove_maximum_hit_point_modifier,
    remove_ongoing_effects,
)
from .effect_lifecycle.turn_hooks import (  # noqa: E402
    _progressed_target_refs,
    _round_duration_expired,
    expire_ongoing_effects_for_turn_start,
    has_condition_save_advantage,
    resolve_end_turn_effects,
)

__all__ = [
    "_progressed_target_refs",
    "_remove_damage_resistances",
    "_remove_effect_target",
    "_remove_effect_tree",
    "_remove_maximum_hit_point_modifier",
    "_required_string",
    "_roll_die",
    "_round_duration_expired",
    "end_concentration",
    "expire_ongoing_effects_for_turn_start",
    "has_condition_save_advantage",
    "remove_ongoing_effects",
    "resolve_concentration_damage",
    "resolve_end_turn_effects",
    "resolve_spell_lifecycle_event",
    "start_ongoing_effect",
]
