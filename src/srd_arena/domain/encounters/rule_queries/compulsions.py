"""Query sourced instructions that constrain a creature's turn."""

from __future__ import annotations

from srd_arena.domain.effects.rule_effects import CompelledTurn

from .context import CreatureEffectQueryContext
from .models import SourcedRuleContribution


def compelled_turns(
    state: CreatureEffectQueryContext,
    target_ref: str,
) -> tuple[SourcedRuleContribution[CompelledTurn], ...]:
    """Return every active instruction compelling the target's current turn."""

    return tuple(
        SourcedRuleContribution(
            ongoing.identity.id,
            ongoing.identity.source,
            rule_effect,
        )
        for ongoing in state.ongoing_effects
        if target_ref in ongoing.target_refs
        for rule_effect in ongoing.rule_effects
        if isinstance(rule_effect, CompelledTurn)
    )


def active_compelled_turn(
    state: CreatureEffectQueryContext,
    target_ref: str,
) -> SourcedRuleContribution[CompelledTurn] | None:
    """Return the most recently applied instruction, if one is active.

    Runtime effects retain application order. Selecting the latest contribution
    gives equal-strength overlapping instructions a deterministic precedence
    without coupling turn orchestration to the spell or feature that created it.
    """

    contributions = compelled_turns(state, target_ref)
    return contributions[-1] if contributions else None
