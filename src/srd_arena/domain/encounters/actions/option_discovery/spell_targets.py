"""Resolve legal spell targets and the context passed to target requirements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....capabilities import (
    HealingEffect,
    TemporaryHitPointsEffect,
    capability_effects,
)
from ....creatures import Creature
from ....effects.conditions import CombatTrait
from ....effects.rule_effects import MaximumHitPointAdjustment
from ....geometry import grid_distance_between
from ....spells.definitions import Spell
from ....spells.resolution import SpellTargetContext
from ....spells.rules import spell_target_disposition
from ...participants import creatures_are_opponents
from ...state_runtime import creature_position
from .spellcasting import spell_range_squares_for, spell_targets_self_only_for

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_action_targets(
    state: EncounterState,
    actor: Creature,
    spell: Spell,
) -> list[SpellTargetContext]:
    """Return target sets for direct, self, area, and staged spell selection.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.geometry import Position
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="mage"),
    ...     creatures={},
    ... )
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_targets."
    ...     "creature_position", return_value=Position(0, 0)
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_targets."
    ...     "spell_range_squares_for", return_value=None
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.option_discovery.spell_targets."
    ...     "spell_targets_self_only_for", return_value=False
    ... ):
    ...     targets = spell_action_targets(
    ...         state, SimpleNamespace(), Spell("bolt", "Bolt", None, 0)
    ...     )
    >>> targets
    []
    """

    creature_ref = state.current_decision().creature_ref
    actor_position = creature_position(state, creature_ref)
    if spell.removable_effect_kinds and not (
        any(
            isinstance(effect, (HealingEffect, TemporaryHitPointsEffect))
            for effect in capability_effects(spell.definition)
        )
    ):
        restoration_targets: list[SpellTargetContext] = []
        max_range = spell_range_squares_for(state, spell, actor)
        for target_ref, target_state in state.creatures.items():
            if not target_state.is_alive:
                continue
            if (
                max_range is not None
                and grid_distance_between(actor_position, target_state.position)
                > max_range
            ):
                continue
            target = spell_target_context(state, actor, target_ref)
            if target is not None and _spell_removal_choices(state, target_ref, spell):
                restoration_targets.append(target)
        return restoration_targets
    if spell.geometry_mode == "point_area":
        max_range = spell_range_squares_for(state, spell, actor)
        if max_range is None:
            return []
        return [
            target
            for target_ref, target_state in state.creatures.items()
            if target_state.is_alive
            and creatures_are_opponents(state, creature_ref, target_ref)
            and grid_distance_between(actor_position, target_state.position)
            <= max_range
            and (target := spell_target_context(state, actor, target_ref)) is not None
        ]
    if spell_targets_self_only_for(state, spell):
        target = spell_target_context(state, actor, creature_ref)
        if target is None:
            return []
        if _spell_removal_choices(state, creature_ref, spell):
            return [target]
        return []

    max_range = spell_range_squares_for(state, spell, actor)
    targets: list[SpellTargetContext] = []
    for target_ref, target_state in state.creatures.items():
        if not target_state.is_alive:
            continue
        disposition = spell_target_disposition(spell)
        is_opponent = creatures_are_opponents(state, creature_ref, target_ref)
        if disposition == "enemy" and not is_opponent:
            continue
        if disposition == "ally" and is_opponent:
            continue
        if disposition == "source" and target_ref != creature_ref:
            continue
        if (
            max_range is not None
            and grid_distance_between(
                actor_position,
                target_state.position,
            )
            > max_range
        ):
            continue
        target = spell_target_context(state, actor, target_ref)
        if target is not None:
            targets.append(target)
    return targets


def _spell_removal_choices(
    state: EncounterState,
    target_ref: str,
    spell: Spell,
) -> tuple[tuple[str, str], ...]:
    target = spell_target_context(
        state,
        state.creatures[state.current_decision().creature_ref].creature,
        target_ref,
    )
    if target is None:
        return ()
    choices: list[tuple[str, str]] = [
        (condition, condition.title())
        for condition in dict.fromkeys(target.target_conditions)
        if condition in spell.removable_conditions
    ]
    if "curse" in spell.removable_effect_kinds:
        choices.extend(
            (
                f"curse@{effect.identity.id}",
                f"Curse: {effect.identity.source.label or effect.identity.source.definition_id}",
            )
            for effect in state.ongoing_effects
            if target_ref in effect.target_refs and effect.kind.value == "curse"
        )
    if "hit_point_maximum_reduction" in spell.removable_effect_kinds and any(
        target_ref in effect.target_refs
        and any(
            isinstance(rule_effect, MaximumHitPointAdjustment) and rule_effect.value < 0
            for rule_effect in effect.rule_effects
        )
        for effect in state.ongoing_effects
    ):
        choices.append(("hit_point_maximum_reduction", "Hit Point Maximum Reduction"))
    return tuple(choices)


def spell_target_context(
    state: EncounterState,
    actor: Creature,
    target_ref: str,
) -> SpellTargetContext | None:
    """Build target facts needed to evaluate authored spell requirements.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(name="Goblin")
    >>> effective = SimpleNamespace(
    ...     providers_for_trait=lambda trait: ("stunned",)
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={
    ...         "goblin": SimpleNamespace(is_alive=True, creature=creature)
    ...     },
    ...     effective_conditions_for=lambda ref: effective,
    ...     conditions_for=lambda ref: (),
    ...     combat_rules=SimpleNamespace(
    ...         condition_immunities=lambda state, ref: SimpleNamespace(
    ...             values=frozenset()
    ...         ),
    ...         apply_damage=lambda state, ref, amount, kind: amount,
    ...         apply_healing=lambda state, ref, amount: amount,
    ...     ),
    ... )
    >>> context = spell_target_context(
    ...     state, SimpleNamespace(), "goblin"
    ... )
    >>> (context.target_label, context.automatic_save_failures["strength"])
    ('Goblin', ('stunned',))
    >>> spell_target_context(state, SimpleNamespace(), "missing") is None
    True
    """

    target_state = state.creatures.get(target_ref)
    if target_state is None or not target_state.is_alive:
        return None
    effective = state.effective_conditions_for(target_ref)
    return SpellTargetContext(
        creature=target_state.creature,
        target_ref=target_ref,
        target_label=target_state.creature.name,
        target_conditions=tuple(
            condition.condition.value for condition in state.conditions_for(target_ref)
        ),
        condition_immunities=frozenset(
            condition.value
            for condition in state.combat_rules.condition_immunities(
                state, target_ref
            ).values
        ),
        damage_receiver=lambda amount, damage_type: state.combat_rules.apply_damage(
            state,
            target_ref,
            amount,
            damage_type,
        ),
        healing_receiver=lambda amount: state.combat_rules.apply_healing(
            state,
            target_ref,
            amount,
        ),
        automatic_save_failures={
            "strength": effective.providers_for_trait(
                CombatTrait.AUTO_FAIL_STRENGTH_SAVES
            ),
            "dexterity": effective.providers_for_trait(
                CombatTrait.AUTO_FAIL_DEXTERITY_SAVES
            ),
        },
    )
