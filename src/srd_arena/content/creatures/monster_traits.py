"""Translate recognized monster-trait tags into intrinsic domain rules."""

from srd_arena.domain.creatures import IntrinsicRuleProvider
from srd_arena.domain.effects.rule_effects import AdjacentAllyAttackAdvantage
from srd_arena.domain.effects.runtime import EffectSourceKind

from .stat_block_schema import BestiaryMonsterSchema


def build_monster_trait_rule_providers(
    stat_block: BestiaryMonsterSchema | None,
) -> dict[str, IntrinsicRuleProvider]:
    """Build typed always-active rules from recognized authored trait tags.

    >>> schema = BestiaryMonsterSchema(
    ...     name="Wolf", source="X", traitTags=["Pack Tactics"]
    ... )
    >>> list(build_monster_trait_rule_providers(schema))
    ['pack_tactics']
    """

    if stat_block is None:
        return {}
    tags = {tag.casefold() for tag in stat_block.trait_tags}
    providers: dict[str, IntrinsicRuleProvider] = {}
    if "pack tactics" in tags:
        providers["pack_tactics"] = IntrinsicRuleProvider(
            id="pack_tactics",
            label="Pack Tactics",
            rule_effects=(AdjacentAllyAttackAdvantage(),),
            source_kind=EffectSourceKind.CREATURE,
        )
    return providers
