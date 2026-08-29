"""Coordinate persistent rule, lifecycle, and condition spell results."""

from ...effects.results import EffectResult
from .context import SpellActionContext
from .persistent_conditions import build_persistent_spell_conditions
from .persistent_parent import build_ongoing_spell_effect
from .persistent_rules import prepare_persistent_rule_plan
from .preparation import PreparedSpellResolution
from .targets import ResolvedSpellTargets


def build_persistent_spell_effects(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    resolved: ResolvedSpellTargets,
) -> list[EffectResult]:
    """Create the parent ongoing effect followed by its condition children.

    No runtime state is created when the spell affected no targets.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityTarget, Outcome,
    ... )
    >>> from ..definitions import Spell
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget('creature'), AutomaticResolution(Outcome())
    ... )
    >>> spell = Spell('ward', 'Ward', 'TEST', 1, definition=definition)
    >>> context = SimpleNamespace(
    ...     spell=spell, selected_condition=None, selected_damage_type=None,
    ...     selected_ability=None, source_ref='mage', current_round=1,
    ...     creature=SimpleNamespace(
    ...         name='Mage',
    ...         spellcasting=SimpleNamespace(save_dc=13, ability_modifier=3),
    ...     ),
    ... )
    >>> prepared = SimpleNamespace(
    ...     definition=definition, definition_effects=(), conditions=(),
    ...     repeat_failure_damage=(), repeat_failure_conditions=(),
    ...     temporary_hit_point_effects=(), roll_modifier_effects=(),
    ...     repeat_save=None, save_ability=None, levels_above=0,
    ...     expires_on_source_turn_end=False,
    ... )
    >>> resolved = SimpleNamespace(affected_targets=())
    >>> build_persistent_spell_effects(context, prepared, resolved)
    []
    """

    rules = prepare_persistent_rule_plan(context, prepared)
    parent = build_ongoing_spell_effect(context, prepared, resolved, rules)
    effects = [parent] if parent is not None else []
    effects.extend(
        build_persistent_spell_conditions(
            context,
            prepared,
            resolved,
            has_parent=parent is not None,
        )
    )
    return effects
