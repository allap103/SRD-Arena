"""Discover executable spell actions from the acting creature's casting grants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....capabilities import (
    ConditionEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    RollModifierEffect,
    capability_effects,
    primary_effects,
)
from ....creatures import Creature, Spellcasting
from ....spells.definitions import Spell
from ....spells.rules import (
    parse_spell_action_ability,
    parse_spell_action_condition,
    parse_spell_action_damage_type,
    parse_spell_action_value,
    spell_action_id,
    spell_action_label,
    spell_action_value,
    spell_supports_higher_level,
)
from ...encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from .spell_targets import _spell_removal_choices, spell_action_targets
from .spellcasting import spell_action_cost

if TYPE_CHECKING:
    from ...encounter import EncounterState


def available_spell_actions(
    self: EncounterState,
    actor: Creature,
) -> list[EncounterAction]:
    """Advertise castable spell grants with target-relative configurations.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(spellcasting=None)
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="fighter")
    ... )
    >>> available_spell_actions(state, actor)
    []
    """

    spellcasting = actor.spellcasting
    creature_ref = self.current_decision().creature_ref
    if spellcasting is None:
        return []
    actions: list[EncounterAction] = []
    for spell in spellcasting.learned_spells:
        cost = spell_action_cost(self, spell)
        if spell.geometry_mode in {"directional_area", "point_area"}:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref),
                    "spell",
                    spell_action_value(spell.id),
                    id=spell_action_id(spell),
                    creature_ref=creature_ref,
                    cost=cost,
                ),
            )
            continue
        targets = spell_action_targets(self, actor, spell)
        shared_effects = capability_effects(spell.definition)
        conditions = tuple(
            effect.condition
            for effect in primary_effects(spell.definition)
            if isinstance(effect, ConditionEffect)
        )
        resistance = next(
            (
                effect
                for effect in shared_effects
                if isinstance(effect, DamageResistanceEffect)
            ),
            None,
        )
        reduction = next(
            (
                effect
                for effect in shared_effects
                if isinstance(effect, DamageReductionEffect)
            ),
            None,
        )
        for target in targets:
            removal_choices = _spell_removal_choices(self, target.target_ref, spell)
            selections = (
                tuple(choice for choice, _label in removal_choices)
                if spell.removable_effect_kinds
                and spell.remove_effect_selection != "all"
                else conditions
                if spell.definition is not None
                and spell.definition.condition_selection == "choose_one"
                else (None,)
            )
            damage_type_selections: tuple[str | None, ...] = (
                (
                    resistance.damage_types
                    if resistance is not None and resistance.selection == "choose_one"
                    else reduction.damage_types
                    if reduction is not None and reduction.selection == "choose_one"
                    else ()
                )
                if (resistance is not None and resistance.selection == "choose_one")
                or (reduction is not None and reduction.selection == "choose_one")
                else (None,)
            )
            ability_choices = tuple(
                ability
                for effect in shared_effects
                if isinstance(effect, RollModifierEffect)
                for ability in effect.ability_options
            )
            ability_selections: tuple[str | None, ...] = (
                ability_choices if ability_choices else (None,)
            )
            for selection in selections:
                for damage_type_selection in damage_type_selections:
                    for ability_selection in ability_selections:
                        _append_spell_option(
                            actions,
                            spellcasting,
                            spell,
                            target.target_ref,
                            creature_ref,
                            cost,
                            selection,
                            removal_choices,
                            damage_type_selection,
                            ability_selection,
                        )
        if not targets:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref),
                    "spell",
                    spell_action_value(spell.id),
                    id=spell_action_id(spell),
                    creature_ref=creature_ref,
                    cost=cost,
                ),
            )
    return actions


def _append_spell_option(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    target_ref: str,
    creature_ref: str,
    cost: ActionCost,
    selection: str | None,
    removal_choices: tuple[tuple[str, str], ...],
    damage_type_selection: str | None,
    ability_selection: str | None,
) -> None:
    selection_display = next(
        (label for choice, label in removal_choices if choice == selection),
        selection.title() if isinstance(selection, str) else "",
    )
    selection_label = f" ({selection_display})" if isinstance(selection, str) else ""
    if damage_type_selection is not None:
        selection_label = f" ({damage_type_selection.title()})"
    if ability_selection is not None:
        selection_label = f" ({ability_selection.title()})"
    selected_id = selection or damage_type_selection or ability_selection
    selection_id = (
        f"-{selected_id.replace(':', '-').replace('@', '-')}" if selected_id else ""
    )
    _append_spell_action_variants(
        actions,
        spellcasting,
        spell,
        EncounterAction(
            spell_action_label(spell, actor_ref=creature_ref) + selection_label,
            "spell",
            spell_action_value(
                spell.id,
                target_ref,
                selected_condition=selection,
                selected_damage_type=damage_type_selection,
                selected_ability=ability_selection,
            ),
            id=spell_action_id(spell, target_ref=target_ref) + selection_id,
            creature_ref=creature_ref,
            cost=cost,
        ),
    )


def _append_spell_action_variants(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    action: EncounterAction,
) -> None:
    actions.append(action)
    if spell.level == 0:
        return
    if not spell_supports_higher_level(spell):
        return
    spell_id, target_ref, aim_point = parse_spell_action_value(str(action.value))
    selected_condition = parse_spell_action_condition(str(action.value))
    selected_damage_type = parse_spell_action_damage_type(str(action.value))
    selected_ability = parse_spell_action_ability(str(action.value))
    for slot_level in sorted(spellcasting.spell_slots_remaining):
        if slot_level <= spell.level:
            continue
        if spellcasting.spell_slots_remaining[slot_level] <= 0:
            continue
        actions.append(
            EncounterAction(
                f"{action.label} (Level {slot_level})",
                action.kind,
                spell_action_value(
                    spell_id,
                    target_ref=target_ref,
                    aim_point=aim_point,
                    selected_condition=selected_condition,
                    selected_damage_type=selected_damage_type,
                    selected_ability=selected_ability,
                    slot_level=slot_level,
                ),
                id=f"{action.id}-level-{slot_level}",
                creature_ref=action.creature_ref,
                cost=action.cost,
            )
        )
