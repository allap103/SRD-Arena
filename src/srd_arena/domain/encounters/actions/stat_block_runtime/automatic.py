"""Resolution for automatic-damage stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....capabilities import DamageEffect
from ....creatures import Creature
from ....creatures.stat_block_actions import AutomaticActionDefinition
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from .resources import consume_stat_block_action_resource
from .rolls import roll_dice

if TYPE_CHECKING:
    from ...encounter import EncounterState


def resolve_automatic_stat_block_action(
    state: EncounterState,
    creature: Creature,
    definition: AutomaticActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Apply a supported automatic stat-block action to one target.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.capabilities import CapabilityTarget
    >>> definition = AutomaticActionDefinition(
    ...     "Aura", CapabilityTarget("creature"), ()
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="monster")
    ... )
    >>> resolve_automatic_stat_block_action(
    ...     state, SimpleNamespace(), definition,
    ...     EncounterAction("Aura", "stat_block"), EncounterProgress(), "aura-1"
    ... )
    Traceback (most recent call last):
    ...
    ValueError: Automatic stat-block action requires a target.
    """
    creature_ref = state.current_decision().creature_ref
    if not isinstance(action.value, str):
        raise ValueError("Automatic stat-block action requires a target.")
    target_ref = action.value
    target = state.creatures[target_ref].creature
    state._consume_action(allow_magic=False)
    consume_stat_block_action_resource(creature, definition.name)
    damage = 0
    damage_details: list[dict[str, object]] = []
    damage_roll_rules = state.combat_rules.roll_modifiers(
        state,
        creature_ref,
        "damage_roll",
    )
    for effect in definition.effects:
        if not isinstance(effect, DamageEffect):
            raise NotImplementedError(
                f"Automatic effect '{type(effect).__name__}' is not executable."
            )
        count_text, sides_text = effect.dice.lower().split("d", 1)
        rolled = roll_dice(int(count_text), int(sides_text))
        sourced_modifier = damage_roll_rules.resolve_modifier(
            lambda sides: roll_dice(1, sides)
        )
        amount = max(
            effect.minimum or 0,
            rolled + effect.bonus + sourced_modifier,
        )
        applied = target.take_damage(amount, effect.damage_type)
        damage += applied
        damage_details.append(
            {
                "damage_type": effect.damage_type,
                "rolled": rolled,
                "bonus": effect.bonus,
                "sourced_modifier": sourced_modifier,
                "applied": applied,
            }
        )
    progress.messages.append(
        (
            "system",
            f"{creature.name} uses {definition.name} on {target.name}, "
            f"dealing {damage} damage.",
        )
    )
    progress.events.append(
        state._event(
            "stat_block_action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "action_name": definition.name,
                "target_ref": target_ref,
                "damage": damage,
                "damage_details": damage_details,
            },
        )
    )
    if target.get_health() <= 0:
        state._remove_relationships_for_creature(target_ref)
        progress.events.append(
            state._event(
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )
