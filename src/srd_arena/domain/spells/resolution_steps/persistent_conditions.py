"""Create provenance-aware condition results for persistent spells."""

from ...effects.results import EffectResult
from .context import SpellActionContext
from .preparation import PreparedSpellResolution
from .targets import ResolvedSpellTargets


def build_persistent_spell_conditions(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    resolved: ResolvedSpellTargets,
    *,
    has_parent: bool,
) -> list[EffectResult]:
    """Create every condition child produced by the resolved casting.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget, Outcome,
    ... )
    >>> from ..definitions import Spell
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("creature"), AutomaticResolution(Outcome())
    ... )
    >>> context = SimpleNamespace(
    ...     spell=Spell("ward", "Ward", "TEST", 1, definition=definition),
    ...     selected_condition=None,
    ... )
    >>> prepared = SimpleNamespace(
    ...     conditions=(), definition=definition,
    ... )
    >>> resolved = SimpleNamespace(affected_targets=())
    >>> build_persistent_spell_conditions(
    ...     context, prepared, resolved, has_parent=False
    ... )
    []
    """

    spell = context.spell
    selected_condition = context.selected_condition
    if selected_condition not in prepared.conditions:
        selected_condition = prepared.conditions[0] if prepared.conditions else None
    selected_conditions = (
        ((selected_condition,) if selected_condition is not None else ())
        if prepared.definition.condition_selection == "choose_one"
        else prepared.conditions
    )
    parent_kind = "concentration" if spell.concentration else "spell"
    results: list[EffectResult] = []
    for target in resolved.affected_targets:
        for condition in selected_conditions:
            condition_data: dict[str, object] = {
                "condition": condition,
                "source_ref": context.source_ref,
                "source_label": context.creature.name,
                "source_kind": "spell",
                "definition_id": spell.id,
            }
            if condition in spell.self_removal_blocked_conditions:
                condition_data["metadata"] = {"blocks_self_removal": True}
            if has_parent:
                condition_data["parent_effect_kind"] = parent_kind
            if prepared.expires_on_source_turn_end:
                condition_data["expires_on_creature_ref"] = context.source_ref
                condition_data["expires_on_round"] = context.current_round + 1
            results.append(
                EffectResult(
                    kind="apply_condition",
                    target_ref=target.target_ref,
                    data=condition_data,
                )
            )
    return results
