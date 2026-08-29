"""Stable public facade for focused spell rule modules."""

from .action_payloads import (
    SpellActionPayload,
    spell_action_id,
    spell_action_label,
    spell_action_payload,
)
from .casting import (
    SpellActionEconomy,
    spell_action_economy,
    spell_cast_block_reason,
)
from .properties import spell_duration_rounds, spell_supports_higher_level
from .targeting import (
    spell_area_shape,
    spell_chooses_area_targets,
    spell_max_targets,
    spell_range_squares,
    spell_repeats_target_allocations,
    spell_requires_full_target_count,
    spell_target_disposition,
    spell_targets_self_only,
)

__all__ = [
    "SpellActionEconomy",
    "SpellActionPayload",
    "spell_action_economy",
    "spell_action_id",
    "spell_action_label",
    "spell_action_payload",
    "spell_area_shape",
    "spell_cast_block_reason",
    "spell_chooses_area_targets",
    "spell_duration_rounds",
    "spell_max_targets",
    "spell_range_squares",
    "spell_repeats_target_allocations",
    "spell_requires_full_target_count",
    "spell_supports_higher_level",
    "spell_target_disposition",
    "spell_targets_self_only",
]
