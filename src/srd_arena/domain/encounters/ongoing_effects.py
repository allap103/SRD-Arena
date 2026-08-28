"""Stable facade for encounter-scoped ongoing-effect lifecycle services.

The implementation is organized by concern under :mod:`effect_lifecycle`.
"""

from __future__ import annotations

from .effect_lifecycle.application import _required_string, start_ongoing_effect
from .effect_lifecycle.concentration import (
    end_concentration,
    resolve_concentration_damage,
)
from .effect_lifecycle.lifecycle_events import resolve_spell_lifecycle_event
from .effect_lifecycle.removal import (
    _remove_effect_target,
    _remove_effect_tree,
    remove_ongoing_effects,
)
from .effect_lifecycle.repeat_saves import resolve_end_turn_effects
from .effect_lifecycle.turn_start import expire_ongoing_effects_for_turn_start

__all__ = [
    "_remove_effect_target",
    "_remove_effect_tree",
    "_required_string",
    "end_concentration",
    "expire_ongoing_effects_for_turn_start",
    "remove_ongoing_effects",
    "resolve_concentration_damage",
    "resolve_end_turn_effects",
    "resolve_spell_lifecycle_event",
    "start_ongoing_effect",
]
