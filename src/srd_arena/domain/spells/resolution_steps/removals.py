"""Build condition and ongoing-effect removals requested by a spell."""

from dataclasses import dataclass

from ...effects.results import EffectResult
from .context import SpellActionContext
from .targets import ResolvedSpellTargets


@dataclass
class SpellRemovalResults:
    """Collect condition and ongoing-effect removals produced by a spell."""

    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    removed_conditions: list[str]


def build_spell_removals(
    context: SpellActionContext,
    resolved: ResolvedSpellTargets,
) -> SpellRemovalResults:
    """Select condition and ongoing-effect applications removed by the spell.

    >>> from types import SimpleNamespace
    >>> from ..definitions import Spell
    >>> spell = Spell(
    ...     "restoration", "Restoration", "TEST", 2,
    ...     removable_conditions=("prone",),
    ...     removable_effect_kinds=("condition",),
    ...     remove_effect_selection="one",
    ... )
    >>> context = SimpleNamespace(spell=spell, selected_condition="prone")
    >>> target = SimpleNamespace(
    ...     target_ref="hero", target_label="Hero",
    ...     target_conditions=("prone",),
    ... )
    >>> resolved = SimpleNamespace(affected_targets=(target,))
    >>> removal = build_spell_removals(context, resolved)
    >>> (removal.removed_conditions, removal.effects[0].kind)
    (['prone'], 'remove_condition')
    """

    spell = context.spell
    messages: list[tuple[str, str]] = []
    effects: list[EffectResult] = []
    removed_conditions: list[str] = []
    if not spell.removable_effect_kinds:
        return SpellRemovalResults(messages, effects, removed_conditions)

    for target in resolved.affected_targets:
        selected_removal = context.selected_condition
        if spell.remove_effect_selection == "all" and spell.removable_conditions:
            target_removed_conditions = tuple(
                condition
                for condition in spell.removable_conditions
                if condition in target.target_conditions
            )
            for condition in target_removed_conditions:
                removed_conditions.append(condition)
                messages.append(
                    (
                        "system",
                        f"{target.target_label} is no longer {condition}.",
                    )
                )
                effects.append(
                    EffectResult(
                        kind="remove_condition",
                        target_ref=target.target_ref,
                        data={"condition": condition},
                    )
                )
        elif selected_removal in spell.removable_conditions:
            if selected_removal not in target.target_conditions:
                continue
            removed_conditions.append(selected_removal)
            messages.append(
                (
                    "system",
                    f"{target.target_label} is no longer {selected_removal}.",
                )
            )
            effects.append(
                EffectResult(
                    kind="remove_condition",
                    target_ref=target.target_ref,
                    data={"condition": selected_removal},
                )
            )
        if "curse" in spell.removable_effect_kinds and (
            spell.remove_effect_selection == "all"
            or (
                isinstance(selected_removal, str)
                and selected_removal.startswith("curse@")
            )
        ):
            effect_id = (
                selected_removal.removeprefix("curse@")
                if isinstance(selected_removal, str)
                and selected_removal.startswith("curse@")
                else None
            )
            effects.append(
                EffectResult(
                    kind="remove_ongoing_effects",
                    target_ref=target.target_ref,
                    data={
                        "effect_kind": "curse",
                        "effect_id": effect_id,
                        "all": spell.remove_effect_selection == "all",
                    },
                )
            )
            messages.append(("system", f"A curse ends on {target.target_label}."))
        if (
            "hit_point_maximum_reduction" in spell.removable_effect_kinds
            and selected_removal == "hit_point_maximum_reduction"
        ):
            effects.append(
                EffectResult(
                    kind="remove_ongoing_effects",
                    target_ref=target.target_ref,
                    data={
                        "parameter": "negative_maximum_hit_points",
                        "all": True,
                    },
                )
            )
            messages.append(
                (
                    "system",
                    f"Hit Point maximum reductions end on {target.target_label}.",
                )
            )
    return SpellRemovalResults(messages, effects, removed_conditions)
