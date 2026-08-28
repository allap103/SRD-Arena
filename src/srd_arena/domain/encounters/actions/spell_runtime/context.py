"""Build the source-neutral context consumed by spell resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....capabilities import (
    AttackResolution,
    ConditionEffect,
    RelationshipRequirement,
    SavingThrowResolution,
    primary_effects,
)
from ....geometry import AreaOfEffect, build_radius_area
from ....rolls.dice import combine_roll_modes
from ....spells.resolution import SpellActionContext, SpellTargetContext
from ....spells.rules import (
    parse_spell_action_ability,
    parse_spell_action_condition,
    parse_spell_action_damage_type,
    parse_spell_healing_allocations,
)
from ...ongoing_effects import has_condition_save_advantage
from .rolls import roll_die

if TYPE_CHECKING:
    from ....creatures import Creature
    from ....spells.definitions import Spell
    from ...encounter import EncounterState


def build_spell_action_context(
    state: EncounterState,
    *,
    actor: Creature,
    spell: Spell,
    spell_value: str,
    creature_ref: str,
    target: SpellTargetContext,
    targets: tuple[SpellTargetContext, ...],
    area: AreaOfEffect | None,
    cast_level: int | None,
) -> SpellActionContext:
    """Supply encounter state needed by otherwise source-neutral resolution.

    Only spells with executable capability definitions may cross this boundary.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.spells import Spell
    >>> try:
    ...     build_spell_action_context(
    ...         SimpleNamespace(), actor=SimpleNamespace(),
    ...         spell=Spell("unknown", "Unknown", None, 1), spell_value="unknown",
    ...         creature_ref="mage", target=SimpleNamespace(), targets=(),
    ...         area=None, cast_level=1,
    ...     )
    ... except AssertionError:
    ...     print("Executable definition required.")
    Executable definition required.
    """

    definition = spell.definition
    assert definition is not None
    attack_mode = (
        definition.resolution.modes[0]
        if isinstance(definition.resolution, AttackResolution)
        else None
    )
    conditions = tuple(
        effect.condition
        for effect in primary_effects(definition)
        if isinstance(effect, ConditionEffect)
    )
    save_advantage_against_opponents = isinstance(
        definition.resolution, SavingThrowResolution
    ) and any(
        modifier.mode == "advantage"
        and any(
            isinstance(requirement, RelationshipRequirement)
            and requirement.relationship == "fighting_source_team"
            for requirement in modifier.requirements
        )
        for modifier in definition.resolution.save_modifiers
    )
    attack_roll_rules = (
        {
            candidate.target_ref: state.combat_rules.roll_modifiers(
                state,
                creature_ref,
                "attack_roll",
            )
            for candidate in targets
        }
        if attack_mode is not None
        else {}
    )
    save_ability = (
        definition.resolution.ability
        if isinstance(definition.resolution, SavingThrowResolution)
        else None
    )
    save_roll_rules = (
        {
            candidate.target_ref: state.combat_rules.roll_modifiers(
                state,
                candidate.target_ref,
                "saving_throw",
                ability=save_ability,
            )
            for candidate in targets
        }
        if save_ability is not None
        else {}
    )
    return SpellActionContext(
        creature=actor,
        spell=spell,
        target=target,
        current_round=state.round_number,
        targets=targets,
        area=area,
        source_ref=creature_ref,
        roller=roll_die,
        selected_condition=parse_spell_action_condition(spell_value),
        selected_damage_type=parse_spell_action_damage_type(spell_value),
        selected_ability=parse_spell_action_ability(spell_value),
        attack_roll_modes=(
            {
                candidate.target_ref: combine_roll_modes(
                    state._attack_roll_mode_for(
                        creature_ref,
                        candidate.target_ref,
                        attack_mode,
                        state._creature_position(creature_ref),
                        tuple(
                            creature_state.position
                            for opponent_ref, creature_state in state.creatures.items()
                            if creature_state.is_alive
                            and state._creatures_are_opponents(
                                creature_ref, opponent_ref
                            )
                        ),
                    ),
                    attack_roll_rules[candidate.target_ref].mode,
                )
                for candidate in targets
            }
            if attack_mode is not None
            else {}
        ),
        attack_roll_modifier_for=lambda _target_ref: state.combat_rules.roll_modifiers(
            state,
            creature_ref,
            "attack_roll",
        ).resolve_modifier(roll_die),
        target_armor_classes={
            candidate.target_ref: state.combat_rules.effective_armor_class(
                state,
                candidate.target_ref,
            ).value
            for candidate in targets
        },
        damage_roll_modifier_for=lambda: state.combat_rules.roll_modifiers(
            state,
            creature_ref,
            "damage_roll",
        ).resolve_modifier(roll_die),
        automatic_critical_providers={
            candidate.target_ref: state._automatic_critical_provider_ids_for(
                creature_ref, candidate.target_ref
            )
            for candidate in targets
        },
        cast_level=cast_level,
        save_roll_modes=(
            {
                candidate.target_ref: "advantage"
                for candidate in targets
                if (
                    has_condition_save_advantage(
                        state,
                        candidate.target_ref,
                        conditions,
                    )
                )
                or (
                    save_advantage_against_opponents
                    and state._creatures_are_opponents(
                        creature_ref, candidate.target_ref
                    )
                )
            }
            if conditions or save_advantage_against_opponents
            else {}
        ),
        save_roll_modifier_for=lambda target_ref, ability: (
            state.combat_rules.roll_modifiers(
                state,
                target_ref,
                "saving_throw",
                ability=ability,
            ).resolve_modifier(roll_die)
        ),
        save_sourced_roll_modes={
            target_ref: rules.mode for target_ref, rules in save_roll_rules.items()
        },
        save_sourced_roll_mode_for=lambda target_ref, ability: (
            state.combat_rules.roll_modifiers(
                state,
                target_ref,
                "saving_throw",
                ability=ability,
            ).mode
        ),
        area_targets_around=lambda center_ref, radius_feet: tuple(
            state._targets_in_area(
                actor,
                build_radius_area(
                    state._creature_position(center_ref),
                    int(
                        state.definition.grid.distance_from_feet(
                            radius_feet,
                            minimum=1,
                        )
                    ),
                    state.definition.grid,
                ),
            )
        ),
        healing_allocations=parse_spell_healing_allocations(spell_value),
    )
