"""Discover executable spell actions from the acting creature's casting grants."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import (
    CompelledTurnEffect,
    ConditionEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    RollModifierEffect,
    TeleportEffect,
    capability_effects,
    primary_effects,
)
from srd_arena.domain.creatures import Creature, Spellcasting
from srd_arena.domain.creatures.feature_rules import (
    spell_invocation_grants,
)
from srd_arena.domain.spells.definitions import Spell
from srd_arena.domain.spells.invocation_grants import SpellInvocationGrant
from srd_arena.domain.spells.rules import (
    SpellActionPayload,
    spell_action_id,
    spell_action_label,
    spell_action_payload,
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
    state: EncounterState,
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
    creature_ref = state.current_decision().creature_ref
    if spellcasting is None:
        return []
    actions: list[EncounterAction] = []
    invocations: list[tuple[Spell, SpellInvocationGrant | None]] = [
        (spell, None) for spell in spellcasting.learned_spells
    ]
    invocations.extend(
        (spell, grant)
        for grant in spell_invocation_grants(actor)
        if (spell := spellcasting.spell_for_grant(grant.spell_id, grant)) is not None
    )
    for spell, grant in invocations:
        cost = spell_action_cost(state, spell)
        grant_label = f" ({grant.source_name})" if grant is not None else ""
        grant_id = grant.id if grant is not None else None
        cast_level = grant.fixed_cast_level if grant is not None else None
        if spell.geometry_mode in {"directional_area", "point_area"}:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref) + grant_label,
                    "spell",
                    spell_action_payload(
                        spell.id,
                        slot_level=cast_level,
                        grant_id=grant_id,
                    ),
                    id=spell_action_id(spell, grant_id=grant_id),
                    creature_ref=creature_ref,
                    aim_committed=False,
                    cost=cost,
                ),
                grant,
            )
            continue
        targets = spell_action_targets(state, actor, spell)
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
            removal_choices = _spell_removal_choices(state, target.target_ref, spell)
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
            option_choices = tuple(
                option
                for effect in shared_effects
                if isinstance(effect, CompelledTurnEffect)
                for option in effect.options
            )
            option_selections: tuple[str | None, ...] = (
                option_choices if option_choices else (None,)
            )
            for selection in selections:
                for damage_type_selection in damage_type_selections:
                    for ability_selection in ability_selections:
                        for option_selection in option_selections:
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
                                option_selection,
                                grant,
                            )
        if not targets:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref) + grant_label,
                    "spell",
                    spell_action_payload(
                        spell.id,
                        slot_level=cast_level,
                        grant_id=grant_id,
                    ),
                    id=spell_action_id(spell, grant_id=grant_id),
                    creature_ref=creature_ref,
                    cost=cost,
                ),
                grant,
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
    option_selection: str | None,
    grant: SpellInvocationGrant | None,
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
    if option_selection is not None:
        selection_label = f" ({option_selection.title()})"
    selected_id = (
        selection or damage_type_selection or ability_selection or option_selection
    )
    selection_id = (
        f"-{selected_id.replace(':', '-').replace('@', '-')}" if selected_id else ""
    )
    _append_spell_action_variants(
        actions,
        spellcasting,
        spell,
        EncounterAction(
            spell_action_label(spell, actor_ref=creature_ref)
            + selection_label
            + (f" ({grant.source_name})" if grant is not None else ""),
            "spell",
            spell_action_payload(
                spell.id,
                target_ref,
                selected_condition=selection,
                selected_damage_type=damage_type_selection,
                selected_ability=ability_selection,
                selected_option=option_selection,
                slot_level=grant.fixed_cast_level if grant is not None else None,
                grant_id=grant.id if grant is not None else None,
            ),
            id=spell_action_id(
                spell,
                target_ref=target_ref,
                grant_id=grant.id if grant is not None else None,
            )
            + selection_id,
            creature_ref=creature_ref,
            cost=cost,
            aim_committed=not any(
                isinstance(effect, TeleportEffect)
                for effect in primary_effects(spell.definition)
            ),
        ),
        grant,
    )


def _append_spell_action_variants(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    action: EncounterAction,
    grant: SpellInvocationGrant | None = None,
) -> None:
    actions.append(action)
    if spell.level == 0 or grant is not None:
        return
    payload = action.value
    if not isinstance(payload, SpellActionPayload):
        raise TypeError("Spell option has no spell payload.")
    for slot_level in sorted(spellcasting.spell_slots_remaining):
        if slot_level <= spell.level:
            continue
        if spellcasting.spell_slots_remaining[slot_level] <= 0:
            continue
        actions.append(
            EncounterAction(
                f"{action.label} (Level {slot_level})",
                action.kind,
                replace(
                    payload,
                    slot_level=slot_level,
                ),
                id=f"{action.id}-level-{slot_level}",
                creature_ref=action.creature_ref,
                aim_committed=action.aim_committed,
                cost=action.cost,
            )
        )
