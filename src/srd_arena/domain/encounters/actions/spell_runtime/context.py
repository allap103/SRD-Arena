"""Build the source-neutral context consumed by spell resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import (
    AttackResolution,
    CapabilityDefinition,
    CapabilityResolution,
    ConditionEffect,
    RelationshipRequirement,
    SavingThrowResolution,
    primary_effects,
)
from srd_arena.domain.geometry import AreaOfEffect
from srd_arena.domain.rolls.dice import D20RollMode
from srd_arena.domain.spells.resolution import SpellActionContext, SpellTargetContext
from srd_arena.domain.spells.rules import SpellActionPayload

from ...participants import creatures_are_opponents
from ...rule_queries.defenses import has_condition_save_advantage
from ...rule_queries.numeric import effective_armor_class
from ...state_combat import (
    attack_roll_mode_for,
    automatic_critical_provider_ids_for,
)
from ...state_runtime import creature_position
from .environment import EncounterSpellResolutionEnvironment

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature
    from srd_arena.domain.spells.definitions import Spell

    from ...encounter import EncounterState


def build_spell_action_context(
    state: EncounterState,
    *,
    actor: Creature,
    spell: Spell,
    payload: SpellActionPayload,
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
    >>> from srd_arena.domain.spells.rules import spell_action_payload
    >>> try:
    ...     build_spell_action_context(
    ...         SimpleNamespace(), actor=SimpleNamespace(),
    ...         spell=Spell("unknown", "Unknown", None, 1),
    ...         payload=spell_action_payload("unknown"),
    ...         creature_ref="mage", target=SimpleNamespace(), targets=(),
    ...         area=None, cast_level=1,
    ...     )
    ... except AssertionError:
    ...     print("Executable definition required.")
    Executable definition required.
    """

    definition = spell.definition
    assert definition is not None
    attack_mode = _spell_attack_mode(definition.resolution)
    conditions = _spell_conditions(definition)
    save_advantage_against_opponents = _saves_favor_opponents(definition.resolution)
    environment = EncounterSpellResolutionEnvironment(state, actor, creature_ref)
    return SpellActionContext(
        creature=actor,
        spell=spell,
        target=target,
        current_round=state.round.number,
        targets=targets,
        area=area,
        source_ref=creature_ref,
        environment=environment,
        selected_condition=payload.selected_condition,
        selected_damage_type=payload.selected_damage_type,
        selected_ability=payload.selected_ability,
        attack_roll_modes=_attack_roll_modes(
            state,
            creature_ref,
            targets,
            attack_mode,
        ),
        target_armor_classes={
            candidate.target_ref: effective_armor_class(
                state,
                candidate.target_ref,
            ).value
            for candidate in targets
        },
        automatic_critical_providers={
            candidate.target_ref: automatic_critical_provider_ids_for(
                state, creature_ref, candidate.target_ref
            )
            for candidate in targets
        },
        cast_level=cast_level,
        save_roll_modes=_save_roll_modes(
            state,
            creature_ref,
            targets,
            conditions,
            save_advantage_against_opponents,
        ),
        healing_allocations=dict(payload.healing_allocations),
    )


def _spell_attack_mode(resolution: CapabilityResolution) -> str | None:
    """Return the authored attack mode when this spell makes an attack."""

    if isinstance(resolution, AttackResolution):
        return resolution.modes[0]
    return None


def _spell_conditions(definition: CapabilityDefinition) -> tuple[str, ...]:
    """Return condition names imposed by the spell's primary effects."""

    return tuple(
        effect.condition
        for effect in primary_effects(definition)
        if isinstance(effect, ConditionEffect)
    )


def _saves_favor_opponents(resolution: CapabilityResolution) -> bool:
    """Return whether targets gain save advantage against opposing casters."""

    return isinstance(resolution, SavingThrowResolution) and any(
        modifier.mode == "advantage"
        and any(
            isinstance(requirement, RelationshipRequirement)
            and requirement.relationship == "fighting_source_team"
            for requirement in modifier.requirements
        )
        for modifier in resolution.save_modifiers
    )


def _attack_roll_modes(
    state: EncounterState,
    creature_ref: str,
    targets: tuple[SpellTargetContext, ...],
    attack_mode: str | None,
) -> dict[str, D20RollMode]:
    """Snapshot spatial and target-derived attack modes for each target."""

    if attack_mode is None:
        return {}
    opponent_positions = tuple(
        creature_state.position
        for opponent_ref, creature_state in state.creatures.items()
        if creature_state.is_alive
        and creatures_are_opponents(state, creature_ref, opponent_ref)
    )
    actor_position = creature_position(state, creature_ref)
    return {
        target.target_ref: attack_roll_mode_for(
            state,
            creature_ref,
            target.target_ref,
            attack_mode,
            actor_position,
            opponent_positions,
        )
        for target in targets
    }


def _save_roll_modes(
    state: EncounterState,
    creature_ref: str,
    targets: tuple[SpellTargetContext, ...],
    conditions: tuple[str, ...],
    favor_opponents: bool,
) -> dict[str, D20RollMode]:
    """Snapshot spell-specific saving-throw modes for each target."""

    if not conditions and not favor_opponents:
        return {}
    return {
        target.target_ref: "advantage"
        for target in targets
        if has_condition_save_advantage(
            state,
            target.target_ref,
            conditions,
        )
        or (
            favor_opponents
            and creatures_are_opponents(state, creature_ref, target.target_ref)
        )
    }
