from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.actor import Actor
from ..models.spellcasting import Spell, Spellcasting
from .behaviors import (
    DIRECTION_DELTAS,
    chebyshev_distance as _chebyshev_distance,
    is_adjacent as _is_adjacent,
)
from .consumables import healing_potions_in_inventory
from .geometry import AreaOfEffect, Vector2D, build_directional_area, vector_between_positions
from .models import ActionCost, EncounterAction
from .refs import enemy_index as _enemy_index, enemy_ref as _enemy_ref
from .spell_actions import SpellTargetContext
from .spells import (
    spell_action_economy,
    spell_action_id,
    spell_action_label,
    spell_action_value,
    spell_cast_block_reason,
    spell_range_squares,
    spell_targets_self_only,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def available_actions(self: EncounterState, player: Actor) -> list[EncounterAction]:
    decision = self.current_decision()
    if self._actor_controller(decision.actor_ref) != "user":
        return []
    if decision.actor_ref != "player":
        return self._user_controlled_enemy_actions(player, decision.actor_ref)
    if decision.kind == "reroll_dice":
        return self._reroll_damage_actions()
    if decision.kind == "reaction":
        return self._reaction_actions()

    actions = []
    if self._player_movement_remaining(player) > 0:
        for direction, (dx, dy) in DIRECTION_DELTAS.items():
            target_x = self.player_position.x + dx
            target_y = self.player_position.y + dy
            if not self._is_within_bounds(target_x, target_y):
                continue
            if self._live_enemy_at(target_x, target_y) is not None:
                continue
            actions.append(
                EncounterAction(
                    f"Move {direction}",
                    "move",
                    direction,
                    id=f"player-move-{direction}",
                    actor_ref="player",
                    cost=ActionCost(movement=1),
                )
            )

    can_attack = self.player_action_available or self.player_attacks_remaining > 0
    for index, enemy in enumerate(self.enemies):
        if (
            can_attack
            and enemy.is_alive
            and self._actors_are_opponents("player", _enemy_ref(index))
            and _is_adjacent(self.player_position, enemy.position)
        ):
            actions.append(
                EncounterAction(
                    f"Attack enemy {index + 1} ({enemy.actor.name})",
                    "attack",
                    index,
                    id=f"player-attack-{index}",
                    actor_ref="player",
                    cost=ActionCost(action=1 if self.player_action_available else 0),
                )
            )

    actions.extend(self._available_feature_actions(player))
    actions.extend(self._available_spell_actions(player))

    if self.player_bonus_action_available:
        for item in healing_potions_in_inventory(player, self.item_templates):
            actions.append(
                EncounterAction(
                    f"Drink {item.name}",
                    "utilize",
                    item.id,
                    id=f"player-utilize-drink-{item.id}",
                    actor_ref="player",
                    cost=ActionCost(bonus_action=1),
                )
            )

    actions.append(
        EncounterAction(
            "Wait",
            "wait",
            id="player-wait",
            actor_ref="player",
        )
    )

    if self.definition.flee and self.definition.flee.allowed:
        actions.append(
            EncounterAction(
                "Flee encounter",
                "flee",
                id="player-flee",
                actor_ref="player",
            )
        )

    return actions


def available_feature_actions(
    self: EncounterState,
    player: Actor,
) -> list[EncounterAction]:
    actions: list[EncounterAction] = []
    for feature_id, definition in player.combat_profile.feature_actions.items():
        if not self._feature_action_available(player, definition):
            continue
        action_cost = ActionCost(
            bonus_action=1 if definition.economy == "bonus_action" else 0,
            action=1 if definition.economy == "action" else 0,
            reaction=1 if definition.economy == "reaction" else 0,
        )
        actions.append(
            EncounterAction(
                definition.label,
                "feature",
                feature_id,
                id=f"player-feature-{feature_id.replace('_', '-')}",
                actor_ref="player",
                cost=action_cost,
            )
        )
    return actions


def available_spell_actions(
    self: EncounterState,
    player: Actor,
) -> list[EncounterAction]:
    spellcasting = player.spellcasting
    if spellcasting is None:
        return []
    actions: list[EncounterAction] = []
    for spell in spellcasting.learned_spells:
        cost = self._spell_action_cost(spell)
        if self._spell_cast_block_reason(spellcasting, spell, cost) is not None:
            continue
        if spell.geometry_mode == "directional_area":
            if not self._spell_action_targets(player, spell):
                continue
            actions.append(
                EncounterAction(
                    spell_action_label(spell),
                    "spell",
                    spell_action_value(spell.id),
                    id=spell_action_id(spell),
                    actor_ref="player",
                    cost=cost,
                )
            )
            continue
        for target in self._spell_action_targets(player, spell):
            actions.append(
                EncounterAction(
                    spell_action_label(
                        spell,
                        target_ref=target.target_ref,
                        target_label=target.target_label,
                    ),
                    "spell",
                    spell_action_value(spell.id, target.target_ref),
                    id=spell_action_id(spell, target_ref=target.target_ref),
                    actor_ref="player",
                    cost=cost,
                )
            )
    return actions


def feature_action_available(self: EncounterState, player: Actor, definition) -> bool:
    if definition.economy == "bonus_action" and not self.player_bonus_action_available:
        return False
    if definition.economy == "action" and not self.player_action_available:
        return False
    if definition.economy == "reaction" and not self.player_reaction_available:
        return False
    return player.feature_uses_remaining.get(definition.feature_id, 0) > 0


def spell_action_cost(self: EncounterState, spell: Spell) -> ActionCost:
    economy = spell_action_economy(spell)
    return ActionCost(
        action=economy.action,
        bonus_action=economy.bonus_action,
        reaction=economy.reaction,
    )


def spell_cast_block_reason_for(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
) -> str | None:
    return spell_cast_block_reason(
        spellcasting,
        spell,
        spell_action_economy(spell),
        action_available=self.player_action_available,
        bonus_action_available=self.player_bonus_action_available,
        reaction_available=self.player_reaction_available,
    )


def spell_targets_self_only_for(self: EncounterState, spell: Spell) -> bool:
    return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(self: EncounterState, spell: Spell, actor: Actor) -> int | None:
    return spell_range_squares(spell, actor)


def spell_action_targets(
    self: EncounterState,
    player: Actor,
    spell: Spell,
) -> list[SpellTargetContext]:
    if self._spell_targets_self_only(spell):
        target = self._spell_target_context(player, "player")
        if target is None:
            return []
        if any(condition in spell.removable_conditions for condition in target.target_conditions):
            return [target]
        return []

    max_range = self._spell_range_squares(spell, player)
    targets: list[SpellTargetContext] = []
    for index, enemy in enumerate(self.enemies):
        target_ref = _enemy_ref(index)
        if not enemy.is_alive or not self._actors_are_opponents("player", target_ref):
            continue
        if max_range is not None and _chebyshev_distance(self.player_position, enemy.position) > max_range:
            continue
        target = self._spell_target_context(player, target_ref)
        if target is not None:
            targets.append(target)
    return targets


def spell_area_targets(
    self: EncounterState,
    player: Actor,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> tuple[SpellTargetContext, ...]:
    area = self._spell_area(player, spell, target_ref=target_ref, aim_point=aim_point)
    if area is None:
        if target_ref is None:
            return ()
        target = self._spell_target_context(player, target_ref)
        return (target,) if target is not None else ()
    return tuple(self._targets_in_area(player, area))


def spend_spell_resources(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
) -> None:
    if cost.action > 0:
        self.player_action_available = False
        self.player_attacks_remaining = 0
    if cost.bonus_action > 0:
        self.player_bonus_action_available = False
    if cost.reaction > 0:
        self.player_reaction_available = False
    if spell.level > 0:
        spellcasting.spell_slots_remaining[spell.level] -= 1


def spell_area(
    self: EncounterState,
    player: Actor,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> AreaOfEffect | None:
    if spell.geometry_mode != "directional_area":
        return None
    if aim_point is not None:
        if abs(aim_point[0] - (self.player_position.x + 0.5)) < 1e-9 and abs(
            aim_point[1] - (self.player_position.y + 0.5)
        ) < 1e-9:
            return None
        direction = Vector2D(
            aim_point[0] - (self.player_position.x + 0.5),
            aim_point[1] - (self.player_position.y + 0.5),
        )
    else:
        if target_ref is None:
            return None
        target = self._spell_target_context(player, target_ref)
        if target is None or target_ref == "player":
            return None
        direction = vector_between_positions(self.player_position, self._actor_position(target_ref))
    length = self._spell_range_squares(spell, player)
    if length is None:
        return None
    coverage_threshold = self.rules_config.directional_aoe_cell_coverage_threshold
    return build_directional_area(
        spell.range_data.get("type"),
        self.player_position,
        direction,
        length,
        self.definition.grid,
        coverage_threshold=coverage_threshold,
    )


def targets_in_area(
    self: EncounterState,
    player: Actor,
    area: AreaOfEffect,
) -> list[SpellTargetContext]:
    occupied_cells = {(cell.x, cell.y) for cell in area.cells}
    targets: list[SpellTargetContext] = []
    if (self.player_position.x, self.player_position.y) in occupied_cells:
        target = self._spell_target_context(player, "player")
        if target is not None:
            targets.append(target)
    for index, enemy in enumerate(self.enemies):
        if not enemy.is_alive:
            continue
        if (enemy.position.x, enemy.position.y) not in occupied_cells:
            continue
        target = self._spell_target_context(player, _enemy_ref(index))
        if target is not None:
            targets.append(target)
    return targets


def spell_target_context(
    self: EncounterState,
    player: Actor,
    target_ref: str,
) -> SpellTargetContext | None:
    if target_ref == "player":
        return SpellTargetContext(
            actor=player,
            target_ref="player",
            target_label=player.name,
            target_conditions=tuple(
                condition.name for condition in self.conditions_for("player")
            ),
        )
    enemy_index = _enemy_index(target_ref)
    if enemy_index < 0 or enemy_index >= len(self.enemies):
        return None
    enemy = self.enemies[enemy_index]
    if not enemy.is_alive:
        return None
    return SpellTargetContext(
        actor=enemy.actor,
        target_ref=target_ref,
        target_label=f"Enemy {enemy_index + 1} ({enemy.actor.name})",
        target_conditions=tuple(
            condition.name for condition in self.conditions_for(target_ref)
        ),
    )
