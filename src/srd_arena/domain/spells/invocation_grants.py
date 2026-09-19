"""Describe alternate, creature-specific ways to invoke authored spells."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SpellInvocationGrant:
    """Authorize one named way of casting a spell with rule-level overrides.

    The grant identifies the source of the permission separately from the spell
    definition. This lets the same spell be cast normally or through a feature
    while both paths still use the shared spell invocation lifecycle.

    >>> grant = SpellInvocationGrant(
    ...     "fiendish_vigor", "false_life", "Fiendish Vigor",
    ...     fixed_cast_level=1, consumes_spell_slot=False,
    ...     temporary_hit_point_dice="maximum",
    ... )
    >>> (grant.spell_id, grant.consumes_spell_slot)
    ('false_life', False)
    """

    id: str
    spell_id: str
    source_name: str
    fixed_cast_level: int | None = None
    consumes_spell_slot: bool = True
    temporary_hit_point_dice: Literal["roll", "maximum"] = "roll"
