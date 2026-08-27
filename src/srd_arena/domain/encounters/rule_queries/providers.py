"""Locate runtime rule effects and their provenance."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from ...effects.rule_effects import RuntimeRuleEffect
from ...effects.runtime import EffectSource, EffectSourceKind
from ..models import CreatureRef

if TYPE_CHECKING:
    from ..encounter import EncounterState


def ongoing_rule_effects(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> Iterator[tuple[str, EffectSource, RuntimeRuleEffect]]:
    """Yield active typed rule effects, once per authored definition.

    Multiple instances retain independent duration and provenance, but effects
    from the same named rule do not stack.  When the active instance ends, the
    next instance becomes the provider automatically.
    """

    active_definitions: set[str] = set()
    for ongoing in state.ongoing_effects:
        definition_id = ongoing.identity.source.definition_id
        if (
            creature_ref not in ongoing.target_refs
            or not ongoing.rule_effects
            or definition_id in active_definitions
        ):
            continue
        active_definitions.add(definition_id)
        for rule_effect in ongoing.rule_effects:
            yield ongoing.identity.id, ongoing.identity.source, rule_effect


def legacy_modifier_provider(
    state: EncounterState,
    creature_ref: CreatureRef,
    definition_id: str,
    origin_id: str,
) -> tuple[str, EffectSource]:
    """Recover provenance for a modifier stored on the legacy Creature model."""

    matching = next(
        (
            ongoing
            for ongoing in state.ongoing_effects
            if creature_ref in ongoing.target_refs
            and ongoing.identity.source.definition_id == definition_id
            and ongoing.identity.source.origin_id == origin_id
        ),
        None,
    )
    if matching is not None:
        return matching.identity.id, matching.identity.source
    provider_state_id = f"creature-modifier:{definition_id}:{origin_id}:{creature_ref}"
    return provider_state_id, EffectSource(
        kind=EffectSourceKind.SYSTEM,
        definition_id=definition_id,
        applied_by_ref=None,
        label=definition_id,
        origin_id=origin_id,
    )
