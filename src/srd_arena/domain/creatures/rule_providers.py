"""Describe always-active rule providers owned by a creature."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.domain.effects.rule_effects import RuntimeRuleEffect
from srd_arena.domain.effects.runtime import EffectSourceKind
from srd_arena.domain.equipment import ArmorCategory


@dataclass(frozen=True)
class IntrinsicRuleProvider:
    """Group sourced rule effects that remain active with their owner.

    Unlike an ongoing effect, an intrinsic provider has no duration or runtime
    application identity. Class features, species traits, and equipped items
    can use this representation when they continuously answer rule queries.
    """

    id: str
    label: str
    rule_effects: tuple[RuntimeRuleEffect, ...]
    source_kind: EffectSourceKind = EffectSourceKind.FEATURE
    blocked_by_armor_categories: frozenset[ArmorCategory] = frozenset()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Intrinsic rule provider requires an ID.")
        if not self.label.strip():
            raise ValueError("Intrinsic rule provider requires a label.")
        if not self.rule_effects:
            raise ValueError(
                "Intrinsic rule provider requires at least one rule effect."
            )
