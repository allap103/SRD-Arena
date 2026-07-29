from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..creatures import Creature, can_grapple
from ..encounters.behaviors import (
    DIRECTION_DELTAS,
    is_adjacent,
)
from ..encounters.models import EncounterAction, EncounterEnemyState
from ..encounters.refs import enemy_ref
from ..geometry import Position
from .attack_resolution import has_free_hand
from .consumables import healing_potion_dice
from .spells.rules import parse_spell_action_value

if TYPE_CHECKING:
    from ..encounters.encounter import EncounterState


@dataclass(frozen=True)
class ActionEligibility:
    allowed: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def allow(cls) -> ActionEligibility:
        return cls(allowed=True)

    @classmethod
    def block(cls, *reasons: str) -> ActionEligibility:
        return cls(allowed=False, reasons=tuple(reason for reason in reasons if reason))

    @property
    def primary_reason(self) -> str | None:
        return self.reasons[0] if self.reasons else None


EligibilityRule = Callable[
    ["EncounterState", Creature, EncounterAction],
    str | None,
]


def evaluate_action(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
    *,
    expected_controller: str = "user",
) -> ActionEligibility:
    """Evaluate the rules shared by action discovery and action execution."""
    action_rules = (
        ACTION_RULES.get(action.kind, ())
        if action.actor_ref == "player"
        else ENEMY_ACTION_RULES.get(action.kind, ())
    )
    reasons = [
        reason
        for reason in (
            _supported_action_rule(state, player, action),
            _actor_rule(
                state,
                player,
                action,
                expected_controller=expected_controller,
            ),
            *(
                rule(state, player, action)
                for rule in (
                _condition_rule,
                _economy_rule,
                    *action_rules,
                )
            ),
        )
        if reason is not None
    ]
    return ActionEligibility.block(*reasons) if reasons else ActionEligibility.allow()


def _supported_action_rule(
    _state: EncounterState,
    _player: Creature,
    action: EncounterAction,
) -> str | None:
    supported_kinds = {
        *(ACTION_RULES if action.actor_ref == "player" else ENEMY_ACTION_RULES),
        "wait",
    }
    return None if action.kind in supported_kinds else "That action is not supported."


def _actor_rule(
    state: EncounterState,
    _player: Creature,
    action: EncounterAction,
    *,
    expected_controller: str,
) -> str | None:
    decision = state.current_decision()
    if decision.actor_ref != action.actor_ref:
        return "That creature is not the current actor."
    if state.rules.controller(decision.actor_ref) != expected_controller:
        return f"That creature is not {expected_controller}-controlled."
    return None


def _condition_rule(
    state: EncounterState,
    _player: Creature,
    action: EncounterAction,
) -> str | None:
    if action.kind in {"wait", "pass", "accept_roll"}:
        return None
    blocking_conditions = {"incapacitated", "stunned"}
    active_conditions = {
        condition.name.casefold()
        for condition in state.conditions_for(action.actor_ref)
    }
    blocked_by = sorted(active_conditions & blocking_conditions)
    if blocked_by:
        return f"You cannot take that action while {blocked_by[0]}."
    return None


def _economy_rule(
    state: EncounterState,
    _player: Creature,
    action: EncounterAction,
) -> str | None:
    if action.actor_ref != "player":
        return None
    if action.cost.action > state.player_actions_remaining:
        return "You have already used your Action."
    if action.cost.bonus_action > 0 and not state.player_bonus_action_available:
        return "You have already used your Bonus Action."
    if action.cost.reaction > 0 and not state.player_reaction_available:
        return "You have already used your Reaction."
    return None


def _move_rule(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    if not isinstance(action.value, str) or action.value not in DIRECTION_DELTAS:
        return "That movement direction is invalid."
    movement_cost = state.rules.movement_cost(player, "player")
    if movement_cost is None:
        return "You cannot move while grappled."
    if state._player_movement_remaining(player) < movement_cost:
        return "You do not have enough movement remaining."

    dx, dy = DIRECTION_DELTAS[action.value]
    moving_refs = {"player", *state.rules.grappling_targets("player")}
    destinations = {
        "player": Position(
            state.player_position.x + dx,
            state.player_position.y + dy,
        ),
        **{
            target_ref: Position(
                state._creature_position(target_ref).x + dx,
                state._creature_position(target_ref).y + dy,
            )
            for target_ref in state.rules.grappling_targets("player")
        },
    }
    if any(
        not state._position_is_free(
            destination.x,
            destination.y,
            ignored_refs=moving_refs,
        )
        for destination in destinations.values()
    ):
        return "You cannot move there."
    return None


def _attack_rule(
    state: EncounterState,
    _player: Creature,
    action: EncounterAction,
) -> str | None:
    target = _target_enemy(state, action)
    if target is None:
        return "That target is not available."
    target_index, enemy = target
    if not state.rules.are_opponents("player", enemy_ref(target_index)):
        return "That creature is not an opponent."
    if not is_adjacent(state.player_position, enemy.position):
        return "The target is out of reach."
    return None


def _grapple_rule(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    target = _target_enemy(state, action)
    if target is None:
        return "That target is not available."
    target_index, enemy = target
    if not state.rules.are_opponents("player", enemy_ref(target_index)):
        return "That creature is not an opponent."
    if not is_adjacent(state.player_position, enemy.position):
        return "The target is out of reach."
    if not has_free_hand(player):
        return "You need a free hand to grapple."
    if not can_grapple(enemy.creature.size, player.size):
        return "The target is too large to grapple."
    return None


def _utilize_rule(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    if not isinstance(action.value, str):
        return "That item is not available."
    item = state.item_templates.get(action.value)
    if item is None or not player.inventory.has_item(action.value):
        return "You do not have that item."
    if healing_potion_dice(item) is None:
        return f"{item.name} cannot be used that way yet."
    return None


def _feature_rule(
    _state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    if not isinstance(action.value, str):
        return "That feature is not available."
    definition = player.combat_profile.feature_actions.get(action.value)
    if definition is None:
        return f"{action.value} is not implemented yet."
    if player.feature_uses_remaining.get(action.value, 0) <= 0:
        return f"You have no uses of {definition.label} remaining."
    return None


def _spell_rule(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    if player.spellcasting is None or not isinstance(action.value, str):
        return "You cannot cast spells."
    try:
        spell_id, target_ref, aim_point = parse_spell_action_value(action.value)
    except ValueError:
        return "That spell is not available."
    spell = next(
        (
            candidate
            for candidate in player.spellcasting.learned_spells
            if candidate.id == spell_id
        ),
        None,
    )
    if spell is None:
        return "That spell is not available."
    block_reason = state.actions.spell_block_reason(
        player.spellcasting,
        spell,
        state.actions.spell_cost(spell),
    )
    if block_reason is not None:
        return block_reason
    if spell.geometry_mode in {"directional_area", "point_area"} and aim_point is None:
        return (
            None
            if state.actions.spell_targets(player, spell)
            else "That target is not available."
        )
    targets = state.actions.spell_area_targets(
        player,
        spell,
        target_ref=target_ref,
        aim_point=aim_point,
    )
    return None if targets else "That target is not available."


def _target_enemy(
    state: EncounterState,
    action: EncounterAction,
) -> tuple[int, EncounterEnemyState] | None:
    if (
        not isinstance(action.value, int)
        or action.value < 0
        or action.value >= len(state.enemies)
    ):
        return None
    enemy = state.enemies[action.value]
    return (action.value, enemy) if enemy.is_alive else None


def _enemy_move_rule(
    state: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> str | None:
    if not isinstance(action.value, str) or action.value not in DIRECTION_DELTAS:
        return "That movement direction is invalid."
    enemy_index = int(action.actor_ref.split(":", 1)[1])
    enemy = state.enemies[enemy_index]
    movement_cost = state.rules.movement_cost(player, action.actor_ref)
    if movement_cost is None:
        return "That creature cannot move while grappled."
    if enemy.movement_remaining is None or enemy.movement_remaining < movement_cost:
        return "That creature does not have enough movement remaining."
    dx, dy = DIRECTION_DELTAS[action.value]
    moving_refs = {
        action.actor_ref,
        *state.rules.grappling_targets(action.actor_ref),
    }
    destinations = {
        action.actor_ref: Position(enemy.position.x + dx, enemy.position.y + dy),
        **{
            target_ref: Position(
                state._creature_position(target_ref).x + dx,
                state._creature_position(target_ref).y + dy,
            )
            for target_ref in state.rules.grappling_targets(action.actor_ref)
        },
    }
    if any(
        not state._position_is_free(
            destination.x,
            destination.y,
            ignored_refs=moving_refs,
        )
        for destination in destinations.values()
    ):
        return "That creature cannot move there."
    return None


def _enemy_attack_rule(
    state: EncounterState,
    _player: Creature,
    action: EncounterAction,
) -> str | None:
    enemy_index = int(action.actor_ref.split(":", 1)[1])
    enemy = state.enemies[enemy_index]
    if not state.rules.are_opponents(action.actor_ref, "player"):
        return "That creature is not an opponent."
    if action.value == "ranged":
        return None
    if not is_adjacent(enemy.position, state.player_position):
        return "The target is out of reach."
    return None


ACTION_RULES: dict[str, tuple[EligibilityRule, ...]] = {
    "move": (_move_rule,),
    "attack": (_attack_rule,),
    "grapple": (_grapple_rule,),
    "utilize": (_utilize_rule,),
    "feature": (_feature_rule,),
    "spell": (_spell_rule,),
}

ENEMY_ACTION_RULES: dict[str, tuple[EligibilityRule, ...]] = {
    "move": (_enemy_move_rule,),
    "attack": (_enemy_attack_rule,),
}
