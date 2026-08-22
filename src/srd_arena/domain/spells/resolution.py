"""Adapt spell actions to the shared capability executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..capabilities.execution import (
    CapabilityExecutionContext,
    CapabilityExecutionStatistics,
    CapabilityTargetContext,
    resolve_capability,
)
from ..capabilities.results import CapabilityActionResult
from ..creatures import Creature
from ..geometry import AreaOfEffect
from ..rolls.dice import D20RollMode
from .definitions import Spell
from .rules import spell_duration_rounds

DieRoller = Callable[[int], int]


@dataclass(frozen=True)
class SpellActionContext:
    """Spell-specific inputs adapted to capability execution."""

    creature: Creature
    spell: Spell
    target: CapabilityTargetContext
    current_round: int
    targets: tuple[CapabilityTargetContext, ...] = ()
    area: AreaOfEffect | None = None
    source_ref: str = "player"
    roller: DieRoller | None = None
    selected_condition: str | None = None
    selected_damage_type: str | None = None
    selected_ability: str | None = None
    attack_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    automatic_critical_providers: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    area_targets_around: (
        Callable[[str, int], tuple[CapabilityTargetContext, ...]] | None
    ) = None
    healing_allocations: dict[str, int] = field(default_factory=dict)


def resolve_spell_action(
    context: SpellActionContext,
) -> CapabilityActionResult | None:
    """Resolve a spell through the provider-neutral capability executor."""
    spell = context.spell
    if spell.definition is None:
        return None
    spellcasting = context.creature.spellcasting
    if spellcasting is None:
        raise ValueError(
            "A creature must have spellcasting statistics to cast a spell."
        )
    cast_level = context.cast_level if context.cast_level is not None else spell.level
    return resolve_capability(
        CapabilityExecutionContext(
            creature=context.creature,
            definition=spell.definition,
            capability_id=spell.id,
            capability_name=spell.name,
            statistics=CapabilityExecutionStatistics(
                save_dc=spellcasting.save_dc,
                attack_bonus=spellcasting.attack_bonus,
                ability_modifier=spellcasting.ability_modifier,
            ),
            target=context.target,
            current_round=context.current_round,
            targets=context.targets,
            area=context.area,
            source_ref=context.source_ref,
            roller=context.roller,
            selected_condition=context.selected_condition,
            selected_damage_type=context.selected_damage_type,
            selected_ability=context.selected_ability,
            attack_roll_modes=context.attack_roll_modes,
            automatic_critical_providers=context.automatic_critical_providers,
            base_resource_level=spell.level,
            resource_level=cast_level,
            duration_rounds=spell_duration_rounds(spell),
            concentration=spell.concentration,
            activation_verb="casts",
            source_kind="spell",
            reactivation_ends_previous=spell.recast_ends_previous,
            blocked_self_removal_conditions=spell.self_removal_blocked_conditions,
            removable_conditions=spell.removable_conditions,
            removable_effect_kinds=spell.removable_effect_kinds,
            remove_effect_selection=spell.remove_effect_selection,
            result_metadata={"spell_level": spell.level, "slot_level": cast_level},
            save_roll_modes=context.save_roll_modes,
            area_targets_around=context.area_targets_around,
            healing_allocations=context.healing_allocations,
        )
    )
