from __future__ import annotations

from copy import deepcopy

from ..features.actions import resolve_feature_action
from .attacks import (
    apply_attack_damage,
    can_make_opportunity_attack,
    damage_roll_detail,
    matching_damage_reroll_rule,
    resolve_attack,
    selected_attack_type,
)
from .behaviors import (
    DIRECTION_DELTAS,
    build_behavior as _build_behavior,
    chebyshev_distance as _chebyshev_distance,
    is_adjacent as _is_adjacent,
    manhattan_distance as _manhattan_distance,
    movement_squares as _movement_squares,
    step_toward as _step_toward,
)
from .consumables import healing_potion_dice, healing_potions_in_inventory
from .effects import apply_effects, serialize_effects
from .geometry import (
    AreaOfEffect,
    Vector2D,
    build_directional_area,
    vector_between_positions,
)
from .models import (
    ActionCost,
    ActorRef,
    AttackOutcome,
    BehaviorContext,
    CombatEvent,
    DecisionFrame,
    DecisionFrameSnapshot,
    EncounterAction,
    EncounterEnemyState,
    EncounterProgress,
    EncounterSnapshot,
    EncounterSnapshotEnemy,
    EncounterStateData,
    PendingAction,
    PendingActionSnapshot,
    PendingAttack,
)
from .pending import restore_pending_attack, snapshot_pending_attack
from .spells import (
    parse_spell_action_value,
    spell_action_economy,
    spell_action_id,
    spell_action_label,
    spell_action_value,
    spell_cast_block_reason,
    spell_range_squares,
    spell_targets_self_only,
)
from ..models.actor import Actor
from ..models.item import Item
from ..models.scene import Encounter, Position
from ..models.spellcasting import Spell, Spellcasting
from ..models.rules_config import RulesConfig
from ..models.status import Status, StatusSnapshot
from ..rules.registry import matching_rules, reroll_eligible_indices
from ..rules.types import RuleGrant
from .spell_actions import SpellActionContext, SpellTargetContext, resolve_spell_action
from ..systems.roll import (
    D20RollMode,
    reroll_dice,
    roll_dice,
    roll_die,
)

class EncounterState(EncounterStateData):
    @classmethod
    def from_definition(
        cls,
        scene_id: str,
        definition: Encounter,
        actor_templates: dict[str, Actor],
        item_templates: dict[str, Item] | None = None,
        control_mode: str = "default",
        rules_config: RulesConfig | None = None,
    ) -> EncounterState:
        enemies = [
            EncounterEnemyState(
                actor_id=enemy.actor_id,
                actor=deepcopy(actor_templates[enemy.actor_id]),
                position=Position(enemy.start.x, enemy.start.y),
                behavior=deepcopy(enemy.behavior),
            )
            for enemy in definition.enemies
        ]
        state = cls(
            scene_id=scene_id,
            definition=definition,
            player_position=Position(
                definition.player_start.x,
                definition.player_start.y,
            ),
            enemies=enemies,
            control_mode=control_mode,
            item_templates=item_templates or {},
            rules_config=rules_config or RulesConfig(),
        )
        state._initialize_behaviors()
        return state

    @classmethod
    def from_snapshot(
        cls,
        definition: Encounter,
        snapshot: EncounterSnapshot,
        actor_templates: dict[str, Actor],
        item_templates: dict[str, Item] | None = None,
        rules_config: RulesConfig | None = None,
    ) -> EncounterState:
        behavior_by_index = {index: enemy.behavior for index, enemy in enumerate(definition.enemies)}
        enemies = []
        for index, saved_enemy in enumerate(snapshot.enemies):
            actor = deepcopy(actor_templates[saved_enemy.actor_id])
            actor.current_health = saved_enemy.current_health
            enemies.append(
                EncounterEnemyState(
                    actor_id=saved_enemy.actor_id,
                    actor=actor,
                    position=Position(saved_enemy.position.x, saved_enemy.position.y),
                    behavior=deepcopy(behavior_by_index[index]),
                    patrol_index=saved_enemy.patrol_index,
                    reaction_available=saved_enemy.reaction_available,
                    movement_remaining=saved_enemy.movement_remaining,
                )
            )
        state = cls(
            scene_id=snapshot.scene_id,
            definition=definition,
            player_position=Position(snapshot.player_position.x, snapshot.player_position.y),
            enemies=enemies,
            control_mode=snapshot.control_mode,
            turn_index=snapshot.turn_index,
            round_number=snapshot.round_number,
            player_movement_remaining=snapshot.player_movement_remaining,
            player_action_available=snapshot.player_action_available,
            player_attacks_remaining=snapshot.player_attacks_remaining,
            player_bonus_action_available=snapshot.player_bonus_action_available,
            player_reaction_available=snapshot.player_reaction_available,
            action_sequence=snapshot.action_sequence,
            frame_sequence=snapshot.frame_sequence,
            event_sequence=snapshot.event_sequence,
            decision_stack=[
                DecisionFrame(
                    id=frame.id,
                    actor_ref=frame.actor_ref,
                    kind=frame.kind,
                    reason=frame.reason,
                    parent_frame_id=frame.parent_frame_id,
                    parent_action_id=frame.parent_action_id,
                    can_pass=frame.can_pass,
                )
                for frame in snapshot.decision_stack
            ],
            pending_action=(
                PendingAction(
                    id=snapshot.pending_action.id,
                    kind=snapshot.pending_action.kind,
                    actor_ref=snapshot.pending_action.actor_ref,
                    direction=snapshot.pending_action.direction,
                    from_position=Position(
                        snapshot.pending_action.from_position.x,
                        snapshot.pending_action.from_position.y,
                    ),
                    to_position=Position(
                        snapshot.pending_action.to_position.x,
                        snapshot.pending_action.to_position.y,
                    ),
                    resume_enemy_index=snapshot.pending_action.resume_enemy_index,
                    remaining_movement_after=snapshot.pending_action.remaining_movement_after,
                    trigger_id=snapshot.pending_action.trigger_id,
                )
                if snapshot.pending_action is not None
                else None
            ),
            pending_attack=restore_pending_attack(snapshot.pending_attack),
            conditions=[
                Status(
                    id=condition.id,
                    name=condition.name,
                    source_ref=condition.source_ref,
                    source_label=condition.source_label,
                    target_ref=condition.target_ref,
                    expires_on_actor_ref=condition.expires_on_actor_ref,
                    expires_on_round=condition.expires_on_round,
                )
                for condition in snapshot.conditions
            ],
            item_templates=item_templates or {},
            rules_config=rules_config or RulesConfig(),
        )
        state._initialize_behaviors()
        state._normalize_turn()
        return state

    def snapshot(self) -> EncounterSnapshot:
        return EncounterSnapshot(
            scene_id=self.scene_id,
            player_position=Position(self.player_position.x, self.player_position.y),
            control_mode=self.control_mode,
            turn_index=self.turn_index,
            round_number=self.round_number,
            player_movement_remaining=self.player_movement_remaining,
            player_action_available=self.player_action_available,
            player_attacks_remaining=self.player_attacks_remaining,
            player_bonus_action_available=self.player_bonus_action_available,
            player_reaction_available=self.player_reaction_available,
            action_sequence=self.action_sequence,
            frame_sequence=self.frame_sequence,
            event_sequence=self.event_sequence,
            decision_stack=[
                DecisionFrameSnapshot(
                    id=frame.id,
                    actor_ref=frame.actor_ref,
                    kind=frame.kind,
                    reason=frame.reason,
                    parent_frame_id=frame.parent_frame_id,
                    parent_action_id=frame.parent_action_id,
                    can_pass=frame.can_pass,
                )
                for frame in self.decision_stack
            ],
            pending_action=(
                PendingActionSnapshot(
                    id=self.pending_action.id,
                    kind=self.pending_action.kind,
                    actor_ref=self.pending_action.actor_ref,
                    direction=self.pending_action.direction,
                    from_position=Position(
                        self.pending_action.from_position.x,
                        self.pending_action.from_position.y,
                    ),
                    to_position=Position(
                        self.pending_action.to_position.x,
                        self.pending_action.to_position.y,
                    ),
                    resume_enemy_index=self.pending_action.resume_enemy_index,
                    remaining_movement_after=self.pending_action.remaining_movement_after,
                    trigger_id=self.pending_action.trigger_id,
                )
                if self.pending_action is not None
                else None
            ),
            pending_attack=snapshot_pending_attack(self.pending_attack),
            conditions=[
                StatusSnapshot(
                    id=condition.id,
                    name=condition.name,
                    source_ref=condition.source_ref,
                    source_label=condition.source_label,
                    target_ref=condition.target_ref,
                    expires_on_actor_ref=condition.expires_on_actor_ref,
                    expires_on_round=condition.expires_on_round,
                )
                for condition in self.conditions
            ],
            enemies=[
                EncounterSnapshotEnemy(
                    actor_id=enemy.actor_id,
                    current_health=enemy.actor.get_health(),
                    position=Position(enemy.position.x, enemy.position.y),
                    patrol_index=enemy.patrol_index,
                    reaction_available=enemy.reaction_available,
                    movement_remaining=enemy.movement_remaining,
                )
                for enemy in self.enemies
            ],
        )

    def _initialize_behaviors(self) -> None:
        self._behaviors = []
        for enemy in self.enemies:
            behavior = _build_behavior(enemy, self.item_templates)
            next(behavior)
            self._behaviors.append(behavior)

    def render(self, player: Actor) -> str:
        player_movement_remaining = self._player_movement_remaining(player)
        rows = []
        for y in range(self.definition.grid.height):
            row = []
            for x in range(self.definition.grid.width):
                if self.player_position.x == x and self.player_position.y == y:
                    row.append("P")
                    continue
                live_enemy = self._live_enemy_at(x, y)
                row.append("E" if live_enemy else ".")
            rows.append(" ".join(row))

        enemy_lines = [
            (
                f"- Enemy {index + 1} ({enemy.actor.name}): "
                f"{enemy.actor.get_health()} HP at ({enemy.position.x}, {enemy.position.y})"
                f"{_condition_suffix(self.conditions_for(_enemy_ref(index)))}"
            )
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
        ]
        if not enemy_lines:
            enemy_lines = ["- No enemies remaining."]

        return "\n".join(
            [
                *rows,
                "",
                f"Round {self.round_number} - Turn: {self.current_turn_label()}",
                f"Movement remaining: {player_movement_remaining}/{_movement_squares(player)} squares",
                (
                    f"Player HP: {player.get_health()}/{player.get_max_health()} "
                    f"at ({self.player_position.x}, {self.player_position.y})"
                    f"{_condition_suffix(self.conditions_for('player'))}"
                ),
                f"Action available: {'yes' if self.player_action_available else 'no'}",
                f"Attacks remaining in action: {self.player_attacks_remaining}",
                f"Reaction available: {'yes' if self.player_reaction_available else 'no'}",
                "Enemies:",
                *enemy_lines,
            ]
        )

    def current_turn_label(self) -> str:
        decision = self.current_decision()
        if decision.kind == "reaction":
            return f"{self._actor_label(decision.actor_ref)} (Reaction)"
        return self._actor_label(decision.actor_ref)

    def current_decision(self) -> DecisionFrame:
        if self.decision_stack:
            return self.decision_stack[-1]
        actor_type, enemy_index = self._active_turn_actor()
        if actor_type == "player":
            return DecisionFrame(
                id="turn-player",
                actor_ref="player",
                kind="turn",
                reason="normal_turn",
            )
        assert enemy_index is not None
        return DecisionFrame(
            id=f"turn-enemy-{enemy_index}",
            actor_ref=_enemy_ref(enemy_index),
            kind="turn",
            reason="normal_turn",
        )

    def conditions_for(self, actor_ref: ActorRef) -> tuple[Status, ...]:
        return tuple(condition for condition in self.conditions if condition.target_ref == actor_ref)

    def has_condition(self, actor_ref: ActorRef, condition_name: str) -> bool:
        return any(
            condition.name == condition_name
            for condition in self.conditions_for(actor_ref)
        )

    def _attack_roll_mode_for(
        self,
        attacker_ref: ActorRef,
        target_ref: ActorRef,
        attack_type: str,
        attacker_position: Position | None,
        nearby_opponent_positions: tuple[Position, ...],
    ) -> D20RollMode:
        modes: list[D20RollMode] = []
        base_mode = _attack_roll_mode(
            attack_type,
            attacker_position,
            nearby_opponent_positions,
        )
        if base_mode != "normal":
            modes.append(base_mode)
        context = {
            "attacker_ref": attacker_ref,
            "target_ref": target_ref,
            "attack_type": attack_type,
        }
        for rule in matching_rules(
            self._active_status_rules(),
            "attack_roll_created",
            context,
        ):
            if rule.operation == "grant_advantage":
                modes.append("advantage")
            elif rule.operation == "grant_disadvantage":
                modes.append("disadvantage")
        return _combine_roll_modes(modes)

    def _active_status_rules(self) -> list[RuleGrant]:
        return [
            rule
            for status in self.conditions
            for rule in status.rules
        ]

    def export_decision(self) -> dict[str, object]:
        decision = self.current_decision()
        payload: dict[str, object] = {
            "frame_id": decision.id,
            "actor_ref": decision.actor_ref,
            "kind": decision.kind,
            "reason": decision.reason,
            "can_pass": decision.can_pass,
            "parent_frame_id": decision.parent_frame_id,
            "parent_action_id": decision.parent_action_id,
        }
        if self.pending_action is not None:
            payload["pending_action_id"] = self.pending_action.id
        return payload

    def export_state(self, player: Actor) -> dict[str, object]:
        active_actor_ref = self.current_decision().actor_ref
        return {
            "scene_id": self.scene_id,
            "grid": {
                "width": self.definition.grid.width,
                "height": self.definition.grid.height,
            },
            "round_number": self.round_number,
            "turn_index": self.turn_index,
            "control_mode": self.control_mode,
            "active_actor_ref": active_actor_ref,
            "active_controller": self._actor_controller(active_actor_ref),
            "player": {
                "actor_id": player.id,
                "name": player.name,
                "position": {"x": self.player_position.x, "y": self.player_position.y},
                "health": player.get_health(),
                "max_health": player.get_max_health(),
                "movement_remaining": self._player_movement_remaining(player),
                "movement_total": _movement_squares(player),
                "movement_remaining_feet": (
                    self._player_movement_remaining(player)
                    * player.attributes.movement.feet_per_square
                ),
                "movement_total_feet": player.attributes.movement.speed_feet,
                "action_available": self.player_action_available,
                "attacks_remaining": self.player_attacks_remaining,
                "bonus_action_available": self.player_bonus_action_available,
                "reaction_available": self.player_reaction_available,
                "conditions": [
                    condition.name for condition in self.conditions_for("player")
                ],
                "spell_slots_max": (
                    {
                        str(level): slots
                        for level, slots in player.spellcasting.spell_slots_max.items()
                    }
                    if player.spellcasting is not None
                    else {}
                ),
                "spell_slots_remaining": (
                    {
                        str(level): slots
                        for level, slots in player.spellcasting.spell_slots_remaining.items()
                    }
                    if player.spellcasting is not None
                    else {}
                ),
                "team_id": self._actor_team_id("player"),
                "controller": self._actor_controller("player"),
            },
            "enemies": [
                {
                    "actor_ref": _enemy_ref(index),
                    "actor_id": enemy.actor_id,
                    "name": enemy.actor.name,
                    "position": {"x": enemy.position.x, "y": enemy.position.y},
                    "health": enemy.actor.get_health(),
                    "reaction_available": enemy.reaction_available,
                    "conditions": [
                        condition.name
                        for condition in self.conditions_for(_enemy_ref(index))
                    ],
                    "movement_remaining": (
                        enemy.movement_remaining
                        if enemy.movement_remaining is not None
                        else _movement_squares(enemy.actor)
                    ),
                    "movement_total": _movement_squares(enemy.actor),
                    "movement_remaining_feet": (
                        (
                            enemy.movement_remaining
                            if enemy.movement_remaining is not None
                            else _movement_squares(enemy.actor)
                        )
                        * enemy.actor.attributes.movement.feet_per_square
                    ),
                    "movement_total_feet": enemy.actor.attributes.movement.speed_feet,
                    "max_health": enemy.actor.get_max_health(),
                    "team_id": self._actor_team_id(_enemy_ref(index)),
                    "controller": self._actor_controller(_enemy_ref(index)),
                    "is_alive": enemy.is_alive,
                }
                for index, enemy in enumerate(self.enemies)
            ],
            "decision": self.export_decision(),
            "pending_action": self._export_pending_action(),
        }

    def active_actor(self) -> tuple[str, int | None]:
        actor_ref = self.current_decision().actor_ref
        if actor_ref == "player":
            return ("player", None)
        return ("enemy", _enemy_index(actor_ref))

    def needs_ai_advance(self) -> bool:
        return self._actor_controller(self.current_decision().actor_ref) == "ai"

    def available_actions(self, player: Actor) -> list[EncounterAction]:
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

    def _available_feature_actions(self, player: Actor) -> list[EncounterAction]:
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

    def _available_spell_actions(self, player: Actor) -> list[EncounterAction]:
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

    def _feature_action_available(self, player: Actor, definition) -> bool:
        if definition.economy == "bonus_action" and not self.player_bonus_action_available:
            return False
        if definition.economy == "action" and not self.player_action_available:
            return False
        if definition.economy == "reaction" and not self.player_reaction_available:
            return False
        return player.feature_uses_remaining.get(definition.feature_id, 0) > 0

    def _spell_action_cost(self, spell: Spell) -> ActionCost:
        economy = spell_action_economy(spell)
        return ActionCost(
            action=economy.action,
            bonus_action=economy.bonus_action,
            reaction=economy.reaction,
        )

    def _spell_cast_block_reason(
        self,
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

    def _spell_targets_self_only(self, spell: Spell) -> bool:
        return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)

    def _spell_range_squares(self, spell: Spell, actor: Actor) -> int | None:
        return spell_range_squares(spell, actor)

    def _spell_action_targets(
        self,
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

    def _spell_area_targets(
        self,
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

    def _spend_spell_resources(
        self,
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

    def _spell_area(
        self,
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
        coverage_threshold = (
            self.rules_config.directional_aoe_cell_coverage_threshold
        )
        return build_directional_area(
            spell.range_data.get("type"),
            self.player_position,
            direction,
            length,
            self.definition.grid,
            coverage_threshold=coverage_threshold,
        )

    def _targets_in_area(
        self,
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

    def apply_action(
        self,
        player: Actor,
        action: EncounterAction,
    ) -> EncounterProgress:
        decision = self.current_decision()
        if self._actor_controller(decision.actor_ref) != "user":
            raise RuntimeError("User action requested for an AI-controlled actor.")
        if decision.actor_ref != "player":
            return self._apply_user_controlled_enemy_action(player, action, decision)
        if decision.kind == "reroll_dice":
            return self._apply_damage_reroll_action(player, action, decision)
        if decision.kind == "reaction":
            return self._apply_reaction_action(player, action, decision)

        progress = EncounterProgress()
        resolved_action_id = self._next_action_id()
        progress.events.append(
            self._event(
                "action_declared",
                actor_ref="player",
                action_id=resolved_action_id,
                data={
                    "kind": action.kind,
                    "value": action.value,
                    "selected_action_id": action.id,
                },
            )
        )
        action_ends_turn = False

        if action.kind == "move":
            direction = str(action.value)
            progress.messages.extend(
                self._resolve_enemy_opportunity_attacks_against_player(
                    player,
                    direction,
                    resolved_action_id,
                    progress,
                )
            )
            if player.get_health() > 0:
                self._apply_player_move(player, direction, progress, resolved_action_id)
        elif action.kind == "attack":
            if not self.player_action_available and self.player_attacks_remaining <= 0:
                progress.messages.append(("system", "You have already used your Action."))
                progress.events.append(
                    self._event(
                        "action_resolved",
                        actor_ref="player",
                        action_id=resolved_action_id,
                        data={"kind": "attack", "success": False},
                    )
                )
                return progress
            if not isinstance(action.value, int):
                raise ValueError(
                    f"Encounter attack action requires an integer target, got {action.value!r}."
                )
            enemy_index = action.value
            enemy = self.enemies[enemy_index]
            target_label = f"Enemy {enemy_index + 1} ({enemy.actor.name})"
            if self.player_action_available:
                self.player_action_available = False
                self.player_attacks_remaining = max(
                    0,
                    player.combat_profile.attacks_per_attack_action - 1,
                )
            elif self.player_attacks_remaining > 0:
                self.player_attacks_remaining -= 1

            attack = resolve_attack(
                player,
                enemy.actor,
                attacker_label=player.name,
                target_label=target_label,
                items_by_id=self.item_templates,
                attacker_position=self.player_position,
                nearby_opponent_positions=tuple(
                    other_enemy.position
                    for other_enemy in self.enemies
                    if other_enemy.is_alive
                ),
                attack_roll_mode_override=self._attack_roll_mode_for(
                    "player",
                    _enemy_ref(enemy_index),
                    selected_attack_type(player, self.item_templates),
                    self.player_position,
                    tuple(
                        other_enemy.position
                        for other_enemy in self.enemies
                        if other_enemy.is_alive
                    ),
                ),
                d20_roller=roll_die,
                dice_roller=roll_dice,
            )
            reroll_rule = matching_damage_reroll_rule(player, attack)
            if attack.hit and reroll_rule is not None:
                self._open_damage_reroll_decision(
                    attack=attack,
                    rule=reroll_rule,
                    target_index=enemy_index,
                    attacker_label=player.name,
                    target_label=target_label,
                    action_id=resolved_action_id,
                    progress=progress,
                )
                return progress
            apply_attack_damage(
                attack,
                enemy.actor,
                attacker_label=player.name,
                target_label=target_label,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={
                        "attacker_label": player.name,
                        "target_ref": _enemy_ref(enemy_index),
                        "target_label": target_label,
                        "attacks_remaining": self.player_attacks_remaining,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                    },
                )
            )
            if not enemy.is_alive:
                progress.events.append(
                    self._event(
                        "actor_defeated",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind == "utilize":
            if not isinstance(action.value, str):
                raise ValueError(
                    f"Encounter utilize action requires an item id, got {action.value!r}."
                )
            self._resolve_utilize_action(player, action.value, progress, resolved_action_id)
        elif action.kind == "feature":
            if not isinstance(action.value, str):
                raise ValueError(
                    f"Encounter feature action requires a feature id, got {action.value!r}."
                )
            self._resolve_feature_action(player, action.value, progress, resolved_action_id)
        elif action.kind == "spell":
            if not isinstance(action.value, str):
                raise ValueError(
                    f"Encounter spell action requires a spell payload, got {action.value!r}."
                )
            self._resolve_spell_action(player, action.value, progress, resolved_action_id)
        elif action.kind == "wait":
            action_ends_turn = True
            progress.messages.append(("system", "You hold your ground."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={"kind": "wait"},
                )
            )
        elif action.kind == "flee":
            progress.messages.append(("system", "You flee the encounter."))
            progress.transition = self.definition.flee.next_scene if self.definition.flee else None
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=resolved_action_id,
                    data={"kind": "flee"},
                )
            )
            return progress

        progress.transition = self._check_transition()
        if progress.transition is not None or player.get_health() <= 0:
            return progress

        if not action_ends_turn:
            return progress

        self._advance_turn()
        self._maybe_reset_reactions()
        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)
        return progress

    def _user_controlled_enemy_actions(
        self,
        player: Actor,
        actor_ref: ActorRef,
    ) -> list[EncounterAction]:
        enemy_index = _enemy_index(actor_ref)
        enemy = self.enemies[enemy_index]
        if enemy.movement_remaining is None:
            enemy.movement_remaining = _movement_squares(enemy.actor)
        actions: list[EncounterAction] = []
        if enemy.movement_remaining > 0:
            for direction, (dx, dy) in DIRECTION_DELTAS.items():
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                if not self._is_free_for_enemy(target_x, target_y):
                    continue
                actions.append(
                    EncounterAction(
                        f"Move {direction}",
                        "move",
                        direction,
                        id=f"{actor_ref}-move-{direction}",
                        actor_ref=actor_ref,
                        cost=ActionCost(movement=1),
                    )
                )
        for target_ref in self._living_actor_refs(player):
            if target_ref == actor_ref or not self._actors_are_opponents(
                actor_ref,
                target_ref,
            ):
                continue
            if not _is_adjacent(enemy.position, self._actor_position(target_ref)):
                continue
            actions.append(
                EncounterAction(
                    f"Attack {self._actor_label(target_ref)}",
                    "attack",
                    target_ref,
                    id=f"{actor_ref}-attack-{target_ref.replace(':', '-')}",
                    actor_ref=actor_ref,
                    cost=ActionCost(action=1),
                )
            )
        actions.append(
            EncounterAction(
                "Wait",
                "wait",
                id=f"{actor_ref}-wait",
                actor_ref=actor_ref,
            )
        )
        return actions

    def _apply_user_controlled_enemy_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        enemy_index = _enemy_index(decision.actor_ref)
        enemy = self.enemies[enemy_index]
        progress = EncounterProgress()
        action_id = self._next_action_id()
        progress.events.append(
            self._event(
                "action_declared",
                actor_ref=decision.actor_ref,
                action_id=action_id,
                data={
                    "kind": action.kind,
                    "value": action.value,
                    "selected_action_id": action.id,
                },
            )
        )
        action_ends_turn = action.kind in {"attack", "wait"}

        if action.kind == "move":
            direction = str(action.value)
            dx, dy = DIRECTION_DELTAS[direction]
            destination = Position(enemy.position.x + dx, enemy.position.y + dy)
            remaining = max(0, (enemy.movement_remaining or 0) - 1)
            if self._queue_player_opportunity_attack(
                player,
                enemy_index,
                action_id,
                direction,
                Position(enemy.position.x, enemy.position.y),
                destination,
                remaining,
                progress,
            ):
                progress.paused_for_decision = True
                return progress
            enemy.position = destination
            enemy.movement_remaining = remaining
            progress.messages.append(
                (
                    "system",
                    f"{enemy.actor.name} moves {direction} to "
                    f"({destination.x}, {destination.y}).",
                )
            )
            progress.events.append(
                self._event(
                    "movement_resolved",
                    actor_ref=decision.actor_ref,
                    action_id=action_id,
                    data={
                        "direction": direction,
                        "to": {"x": destination.x, "y": destination.y},
                    },
                )
            )
        elif action.kind == "attack":
            if not isinstance(action.value, str):
                raise ValueError("Attack action requires an actor reference.")
            target_ref = action.value
            if not self._actors_are_opponents(decision.actor_ref, target_ref):
                raise ValueError("Attack target must belong to an opposing team.")
            defender = self._actor_for_ref(player, target_ref)
            target_label = self._actor_label(target_ref)
            attacker_label = self._actor_label(decision.actor_ref)
            attack = resolve_attack(
                enemy.actor,
                defender,
                attacker_label=attacker_label,
                target_label=target_label,
                items_by_id=self.item_templates,
                attacker_position=enemy.position,
                nearby_opponent_positions=(self.player_position,),
                attack_roll_mode_override=self._attack_roll_mode_for(
                    decision.actor_ref,
                    target_ref,
                    selected_attack_type(enemy.actor, self.item_templates),
                    enemy.position,
                    (self.player_position,),
                ),
                d20_roller=roll_die,
                dice_roller=roll_dice,
            )
            apply_attack_damage(
                attack,
                defender,
                attacker_label=attacker_label,
                target_label=target_label,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref=decision.actor_ref,
                    action_id=action_id,
                    data={
                        "attacker_label": attacker_label,
                        "target_ref": target_ref,
                        "target_label": target_label,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                    },
                )
            )
            if defender.get_health() <= 0:
                progress.events.append(
                    self._event(
                        "actor_defeated",
                        actor_ref=target_ref,
                        action_id=action_id,
                    )
                )
        elif action.kind == "wait":
            progress.messages.append(("system", f"{enemy.actor.name} waits."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref=decision.actor_ref,
                    action_id=action_id,
                    data={"kind": "wait"},
                )
            )
        else:
            raise ValueError(f"Unsupported user-controlled enemy action: {action.kind}")

        progress.transition = self._check_transition()
        if (
            progress.transition is not None
            or player.get_health() <= 0
            or not action_ends_turn
        ):
            return progress
        self._advance_turn()
        self._maybe_reset_reactions()
        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)
        return progress

    def _open_damage_reroll_decision(
        self,
        *,
        attack: AttackOutcome,
        rule: RuleGrant,
        target_index: int,
        attacker_label: str,
        target_label: str,
        action_id: str,
        progress: EncounterProgress,
        continuation: str = "return_to_turn",
        reaction: bool = False,
    ) -> None:
        frame_id = self._next_frame_id()
        current_frame = self.current_decision()
        self.pending_attack = PendingAttack(
            action_id=action_id,
            attacker_ref="player",
            target_ref=_enemy_ref(target_index),
            target_index=target_index,
            attacker_label=attacker_label,
            target_label=target_label,
            attacks_remaining=self.player_attacks_remaining,
            attack=attack,
            rule=rule,
            continuation=continuation,
            reaction=reaction,
        )
        self.decision_stack.append(
            DecisionFrame(
                id=frame_id,
                actor_ref="player",
                kind="reroll_dice",
                reason=rule.id,
                parent_frame_id=current_frame.id,
                parent_action_id=action_id,
                can_pass=True,
            )
        )
        progress.messages.extend(attack.messages)
        attack.messages = []
        progress.messages.append(
            (
                "system",
                f"{rule.id.replace('_', ' ').title()} can reroll qualifying damage dice.",
            )
        )
        progress.events.append(
            self._event(
                "attack_pending",
                actor_ref="player",
                frame_id=frame_id,
                action_id=action_id,
                data=self._pending_attack_event_data(),
            )
        )
        progress.paused_for_decision = True

    def _reroll_damage_actions(self) -> list[EncounterAction]:
        pending = self.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            return []
        actions = [
            EncounterAction(
                f"Reroll damage die {index + 1} ({pending.attack.damage_roll.dice[index].result})",
                "reroll_die",
                index,
                id=_reroll_die_action_id(pending.action_id, index),
                actor_ref="player",
            )
            for index in reroll_eligible_indices(
                pending.rule,
                pending.attack.damage_roll,
            )
        ]
        actions.append(
            EncounterAction(
                "Use current damage",
                "accept_roll",
                id=f"{pending.action_id}-accept-damage",
                actor_ref="player",
            )
        )
        return actions

    def _apply_damage_reroll_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        pending = self.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            raise RuntimeError("Damage reroll requested without a pending attack.")
        progress = EncounterProgress()
        progress.events.append(
            self._event(
                "action_declared",
                actor_ref="player",
                frame_id=decision.id,
                action_id=pending.action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "reroll_die":
            if not isinstance(action.value, int):
                raise ValueError("Reroll die action requires an integer die index.")
            eligible = reroll_eligible_indices(
                pending.rule,
                pending.attack.damage_roll,
            )
            if action.value not in eligible:
                raise ValueError(f"Damage die {action.value} is not eligible for reroll.")
            previous = pending.attack.damage_roll.dice[action.value].result
            pending.attack.damage_roll = reroll_dice(
                pending.attack.damage_roll,
                [action.value],
                roller=lambda sides: roll_dice(1, sides),
            )
            replacement = pending.attack.damage_roll.dice[action.value].result
            pending.attack.damage_roll_detail = damage_roll_detail(pending.attack)
            progress.messages.append(
                (
                    "system",
                    f"Damage die {action.value + 1} rerolled: {previous} -> {replacement}.",
                )
            )
            progress.events.append(
                self._event(
                    "damage_rerolled",
                    actor_ref="player",
                    frame_id=decision.id,
                    action_id=pending.action_id,
                    data=self._pending_attack_event_data(),
                )
            )
            if reroll_eligible_indices(pending.rule, pending.attack.damage_roll):
                progress.paused_for_decision = True
                return progress
        elif action.kind != "accept_roll":
            raise ValueError(f"Unsupported damage reroll action: {action.kind}")

        self._finalize_pending_attack(player, progress, decision)
        return progress

    def _finalize_pending_attack(
        self,
        player: Actor,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        pending = self.pending_attack
        if pending is None:
            raise RuntimeError("Cannot finalize an attack that is not pending.")
        target = self.enemies[pending.target_index]
        apply_attack_damage(
            pending.attack,
            target.actor,
            attacker_label=player.name,
            target_label=pending.target_label,
        )
        progress.messages.extend(pending.attack.messages)
        progress.events.append(
            self._event(
                "attack_resolved",
                actor_ref="player",
                frame_id=decision.id,
                action_id=pending.action_id,
                data={
                    **self._pending_attack_event_data(),
                    "hit": True,
                    "damage": pending.attack.damage,
                    "damage_roll_detail": pending.attack.damage_roll_detail,
                    "eligible_die_indices": [],
                    "reroll_action_ids": {},
                    "accept_action_id": None,
                },
            )
        )
        if not target.is_alive:
            progress.events.append(
                self._event(
                    "actor_defeated",
                    actor_ref=pending.target_ref,
                    frame_id=decision.id,
                    action_id=pending.action_id,
                )
            )
        self.pending_attack = None
        self.decision_stack.pop()
        progress.events.append(
            self._event(
                "decision_closed",
                actor_ref="player",
                frame_id=decision.id,
                action_id=pending.action_id,
            )
        )
        progress.transition = self._check_transition()
        if (
            pending.continuation == "complete_reaction"
            and progress.transition is None
            and player.get_health() > 0
        ):
            self._complete_parent_reaction(player, progress, pending.action_id)

    def _complete_parent_reaction(
        self,
        player: Actor,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        reaction = self.current_decision()
        if reaction.kind != "reaction":
            raise RuntimeError(
                "Pending attack expected to resume a reaction, "
                f"but current decision is '{reaction.kind}'."
            )
        self.decision_stack.pop()
        progress.events.append(
            self._event(
                "decision_closed",
                actor_ref="player",
                frame_id=reaction.id,
                action_id=action_id,
            )
        )
        self._resume_pending_action(player, progress)
        progress.transition = self._check_transition()
        if progress.transition is not None or player.get_health() <= 0:
            return
        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)

    def _pending_attack_event_data(self) -> dict[str, object]:
        pending = self.pending_attack
        if pending is None or pending.attack.damage_roll is None:
            return {}
        eligible = reroll_eligible_indices(
            pending.rule,
            pending.attack.damage_roll,
        )
        return {
            "attacker_label": pending.attacker_label,
            "target_ref": pending.target_ref,
            "target_label": pending.target_label,
            "attacks_remaining": pending.attacks_remaining,
            "attack_roll": pending.attack.attack_roll,
            "attack_roll_detail": pending.attack.attack_roll_detail,
            "hit": True,
            "critical_hit": pending.attack.critical_hit,
            "damage": 0,
                    "damage_roll_detail": damage_roll_detail(pending.attack),
            "roll_id": f"{pending.action_id}:damage",
            "rule_id": pending.rule.id,
            "eligible_die_indices": list(eligible),
            "reroll_action_ids": {
                str(index): _reroll_die_action_id(pending.action_id, index)
                for index in eligible
            },
            "accept_action_id": f"{pending.action_id}-accept-damage",
            "reaction": pending.reaction,
        }

    def advance_until_next_decision(self, player: Actor) -> EncounterProgress:
        progress = EncounterProgress()
        ai_actions_resolved = 0
        while True:
            if player.get_health() <= 0:
                break
            if self.decision_stack and self._actor_controller(
                self.current_decision().actor_ref
            ) == "user":
                progress.paused_for_decision = True
                break
            actor_type, enemy_index = self._active_turn_actor()
            actor_ref = (
                "player"
                if actor_type == "player"
                else _enemy_ref(enemy_index if enemy_index is not None else 0)
            )
            if self._actor_controller(actor_ref) == "user":
                progress.paused_for_decision = True
                break
            if actor_type == "player":
                break
            assert enemy_index is not None
            remaining_limit = (
                None
                if self.ai_action_limit is None
                else self.ai_action_limit - ai_actions_resolved
            )
            completed_turn, enemy_progress, actions_resolved = self._run_enemy_turn(
                player,
                enemy_index,
                action_limit=remaining_limit,
            )
            ai_actions_resolved += actions_resolved
            self._merge_progress(progress, enemy_progress)
            if progress.transition is not None or progress.paused_for_decision:
                break
            if completed_turn:
                self._advance_turn()
                self._maybe_reset_reactions()
                progress.transition = self._check_transition()
                if progress.transition is not None:
                    break
            if (
                self.ai_action_limit is not None
                and ai_actions_resolved >= self.ai_action_limit
            ):
                progress.paused_for_ai = True
                break
        return progress

    def _run_enemy_turn(
        self,
        player: Actor,
        enemy_index: int,
        *,
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        enemy = self.enemies[enemy_index]
        progress = EncounterProgress()
        if not enemy.is_alive:
            return True, progress, 0
        if enemy.movement_remaining is None:
            enemy.movement_remaining = _movement_squares(enemy.actor)

        behavior = self._behaviors[enemy_index]
        actions_resolved = 0
        while enemy.is_alive and player.get_health() > 0:
            command = behavior.send(
                BehaviorContext(
                    player_position=Position(self.player_position.x, self.player_position.y),
                    enemy_position=Position(enemy.position.x, enemy.position.y),
                    can_attack=(
                        _is_adjacent(self.player_position, enemy.position)
                        and self._actors_are_opponents(
                            _enemy_ref(enemy_index),
                            "player",
                        )
                    ),
                )
            )
            if command is None:
                break

            action_id = self._next_action_id()
            progress.events.append(
                self._event(
                    "action_declared",
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": command.kind, "value": command.value},
                )
            )

            if command.kind == "move":
                if enemy.movement_remaining <= 0:
                    break
                direction = str(command.value)
                dx, dy = DIRECTION_DELTAS[direction]
                target_x = enemy.position.x + dx
                target_y = enemy.position.y + dy
                if not self._is_free_for_enemy(target_x, target_y):
                    break
                if self._queue_player_opportunity_attack(
                    player,
                    enemy_index,
                    action_id,
                    direction,
                    Position(enemy.position.x, enemy.position.y),
                    Position(target_x, target_y),
                    enemy.movement_remaining - 1,
                    progress,
                ):
                    progress.paused_for_decision = True
                    return False, progress, actions_resolved
                enemy.position = Position(target_x, target_y)
                enemy.movement_remaining -= 1
                actions_resolved += 1
                progress.messages.append(
                    (
                        "system",
                        f"{enemy.actor.name} moves {direction} to ({target_x}, {target_y}).",
                    )
                )
                progress.events.append(
                    self._event(
                        "movement_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "direction": direction,
                            "to": {"x": target_x, "y": target_y},
                        },
                    )
                )
                if action_limit is not None and actions_resolved >= action_limit:
                    return False, progress, actions_resolved
                continue

            if command.kind == "attack":
                preferred_attack_type = (
                    str(command.value)
                    if isinstance(command.value, str) and command.value in {"melee", "ranged"}
                    else None
                )
                attack = resolve_attack(
                    enemy.actor,
                    player,
                    attacker_label=f"Enemy {enemy_index + 1} ({enemy.actor.name})",
                    target_label=player.name,
                    items_by_id=self.item_templates,
                    attacker_position=enemy.position,
                    nearby_opponent_positions=(self.player_position,),
                    preferred_attack_type=preferred_attack_type,
                    attack_roll_mode_override=self._attack_roll_mode_for(
                        _enemy_ref(enemy_index),
                        "player",
                        selected_attack_type(
                            enemy.actor,
                            self.item_templates,
                            preferred_attack_type=preferred_attack_type,
                        ),
                        enemy.position,
                        (self.player_position,),
                    ),
                    d20_roller=roll_die,
                    dice_roller=roll_dice,
                )
                apply_attack_damage(
                    attack,
                    player,
                    attacker_label=f"Enemy {enemy_index + 1} ({enemy.actor.name})",
                    target_label=player.name,
                )
                progress.messages.extend(attack.messages)
                progress.events.append(
                    self._event(
                        "attack_resolved",
                        actor_ref=_enemy_ref(enemy_index),
                        action_id=action_id,
                        data={
                            "attacker_label": f"Enemy {enemy_index + 1} ({enemy.actor.name})",
                            "target_ref": "player",
                            "target_label": player.name,
                            "attack_roll": attack.attack_roll,
                            "attack_roll_detail": attack.attack_roll_detail,
                            "hit": attack.hit,
                            "critical_hit": attack.critical_hit,
                            "damage": attack.damage,
                            "damage_roll_detail": attack.damage_roll_detail,
                        },
                    )
                )
                actions_resolved += 1
                return True, progress, actions_resolved

            progress.messages.append(("system", f"{enemy.actor.name} waits."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref=_enemy_ref(enemy_index),
                    action_id=action_id,
                    data={"kind": "wait"},
                )
            )
            actions_resolved += 1
            return True, progress, actions_resolved
        return True, progress, actions_resolved

    def _apply_reaction_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        progress = EncounterProgress()
        pending_action = self.pending_action
        if pending_action is None:
            raise RuntimeError("Reaction action requested without a pending action.")
        resolved_action_id = self._next_action_id()

        progress.events.append(
            self._event(
                "action_declared",
                actor_ref="player",
                frame_id=decision.id,
                action_id=resolved_action_id,
                data={"kind": action.kind, "selected_action_id": action.id},
            )
        )

        if action.kind == "opportunity_attack":
            self.player_reaction_available = False
            target_index = _enemy_index(pending_action.actor_ref)
            target = self.enemies[target_index]
            target_label = f"Enemy {target_index + 1} ({target.actor.name})"
            attack = resolve_attack(
                player,
                target.actor,
                attacker_label=player.name,
                target_label=target_label,
                action_label="Opportunity attack",
                items_by_id=self.item_templates,
                attacker_position=self.player_position,
                nearby_opponent_positions=(target.position,),
                preferred_attack_type="melee",
                attack_roll_mode_override=self._attack_roll_mode_for(
                    "player",
                    pending_action.actor_ref,
                    "melee",
                    self.player_position,
                    (target.position,),
                ),
                d20_roller=roll_die,
                dice_roller=roll_dice,
            )
            reroll_rule = matching_damage_reroll_rule(player, attack)
            if attack.hit and reroll_rule is not None:
                self._open_damage_reroll_decision(
                    attack=attack,
                    rule=reroll_rule,
                    target_index=target_index,
                    attacker_label=player.name,
                    target_label=target_label,
                    action_id=resolved_action_id,
                    progress=progress,
                    continuation="complete_reaction",
                    reaction=True,
                )
                return progress
            apply_attack_damage(
                attack,
                target.actor,
                attacker_label=player.name,
                target_label=target_label,
            )
            progress.messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref="player",
                    frame_id=decision.id,
                    action_id=resolved_action_id,
                    data={
                        "attacker_label": player.name,
                        "target_ref": pending_action.actor_ref,
                        "target_label": target_label,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if not target.is_alive:
                progress.events.append(
                    self._event(
                        "actor_defeated",
                        actor_ref=pending_action.actor_ref,
                        frame_id=decision.id,
                        action_id=resolved_action_id,
                    )
                )
        elif action.kind != "pass":
            raise ValueError(f"Unsupported reaction action: {action.kind}")

        self.decision_stack.pop()
        progress.events.append(
            self._event(
                "decision_closed",
                actor_ref="player",
                frame_id=decision.id,
                action_id=resolved_action_id,
            )
        )

        self._resume_pending_action(player, progress)
        progress.transition = self._check_transition()
        if progress.transition is not None or player.get_health() <= 0:
            return progress

        follow_up = self.advance_until_next_decision(player)
        self._merge_progress(progress, follow_up)
        return progress

    def _resume_pending_action(self, player: Actor, progress: EncounterProgress) -> None:
        pending_action = self.pending_action
        if pending_action is None:
            return
        self.pending_action = None
        if pending_action.kind != "move":
            return

        if pending_action.actor_ref == "player":
            return

        enemy_index = _enemy_index(pending_action.actor_ref)
        enemy = self.enemies[enemy_index]
        if enemy.is_alive and self._is_free_for_enemy(
            pending_action.to_position.x,
            pending_action.to_position.y,
        ):
            enemy.position = Position(
                pending_action.to_position.x,
                pending_action.to_position.y,
            )
            progress.messages.append(
                (
                    "system",
                    f"{enemy.actor.name} moves {pending_action.direction} to "
                    f"({pending_action.to_position.x}, {pending_action.to_position.y}).",
                )
            )
            progress.events.append(
                self._event(
                    "movement_resolved",
                    actor_ref=pending_action.actor_ref,
                    action_id=pending_action.id,
                    data={
                        "direction": pending_action.direction,
                        "to": {
                            "x": pending_action.to_position.x,
                            "y": pending_action.to_position.y,
                        },
                        "resumed": True,
                    },
                )
            )

        if pending_action.resume_enemy_index is None:
            return
        if self._actor_controller(pending_action.actor_ref) == "user":
            enemy.movement_remaining = pending_action.remaining_movement_after
            return
        enemy.movement_remaining = pending_action.remaining_movement_after
        if self.ai_action_limit is not None:
            return
        completed_turn, resumed, _ = self._run_enemy_turn(
            player,
            pending_action.resume_enemy_index,
        )
        self._merge_progress(progress, resumed)
        if completed_turn and not progress.paused_for_decision:
            self._advance_turn()
            self._maybe_reset_reactions()

    def _resolve_enemy_opportunity_attacks_against_player(
        self,
        player: Actor,
        direction: str,
        action_id: str,
        progress: EncounterProgress,
    ) -> list[tuple[str, str]]:
        dx, dy = DIRECTION_DELTAS[direction]
        origin = Position(self.player_position.x, self.player_position.y)
        destination = Position(self.player_position.x + dx, self.player_position.y + dy)
        messages: list[tuple[str, str]] = []
        threatened_by = [
            (index, enemy)
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
            and self._actors_are_opponents(_enemy_ref(index), "player")
            and enemy.reaction_available
            and can_make_opportunity_attack(enemy.actor, self.item_templates)
            and _is_adjacent(origin, enemy.position)
            and not _is_adjacent(destination, enemy.position)
        ]
        for index, enemy in threatened_by:
            enemy.reaction_available = False
            trigger_id = self._next_frame_id(prefix="trigger")
            progress.events.append(
                self._event(
                    "trigger_opened",
                    actor_ref=_enemy_ref(index),
                    action_id=action_id,
                    data={"kind": "opportunity_attack", "trigger_id": trigger_id},
                )
            )
            attack = resolve_attack(
                enemy.actor,
                player,
                attacker_label=f"Enemy {index + 1} ({enemy.actor.name})",
                target_label=player.name,
                action_label="Opportunity attack",
                items_by_id=self.item_templates,
                attacker_position=enemy.position,
                nearby_opponent_positions=(self.player_position,),
                preferred_attack_type="melee",
                attack_roll_mode_override=self._attack_roll_mode_for(
                    _enemy_ref(index),
                    "player",
                    "melee",
                    enemy.position,
                    (self.player_position,),
                ),
                d20_roller=roll_die,
                dice_roller=roll_dice,
            )
            apply_attack_damage(
                attack,
                player,
                attacker_label=f"Enemy {index + 1} ({enemy.actor.name})",
                target_label=player.name,
            )
            messages.extend(attack.messages)
            progress.events.append(
                self._event(
                    "attack_resolved",
                    actor_ref=_enemy_ref(index),
                    action_id=action_id,
                    data={
                        "attacker_label": f"Enemy {index + 1} ({enemy.actor.name})",
                        "target_ref": "player",
                        "target_label": player.name,
                        "attack_roll": attack.attack_roll,
                        "attack_roll_detail": attack.attack_roll_detail,
                        "hit": attack.hit,
                        "critical_hit": attack.critical_hit,
                        "damage": attack.damage,
                        "damage_roll_detail": attack.damage_roll_detail,
                        "reaction": True,
                    },
                )
            )
            if player.get_health() <= 0:
                break
        return messages

    def _resolve_utilize_action(
        self,
        player: Actor,
        item_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        item = self.item_templates.get(item_id)
        if item is None or not player.inventory.has_item(item_id):
            progress.messages.append(("system", "You do not have that item."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "utilize", "item_id": item_id, "success": False},
                )
            )
            return

        if not self.player_bonus_action_available:
            progress.messages.append(("system", "You have already used your Bonus Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={
                        "kind": "utilize",
                        "item_id": item.id,
                        "item_name": item.name,
                        "success": False,
                    },
                )
            )
            return

        healing_dice = healing_potion_dice(item)
        if healing_dice is None:
            progress.messages.append(("system", f"{item.name} cannot be used that way yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={
                        "kind": "utilize",
                        "item_id": item.id,
                        "item_name": item.name,
                        "success": False,
                    },
                )
            )
            return

        dice_count, dice_sides, modifier = healing_dice
        dice_total = roll_dice(dice_count, dice_sides)
        healing_total = dice_total + modifier
        applied_healing = player.heal(healing_total)
        consumed = item.has_misc_tag("CNS")
        if consumed:
            player.inventory.remove_item(item.id)
        self.player_bonus_action_available = False

        modifier_text = f" + {modifier}" if modifier else ""
        progress.messages.extend(
            [
                ("system", f"{player.name} drinks {item.name}."),
                (
                    "system",
                    f"Healing: {dice_count}d{dice_sides}={dice_total}{modifier_text} "
                    f"= {healing_total}; applied {applied_healing}.",
                ),
            ]
        )
        if consumed:
            progress.messages.append(("system", f"{item.name} is consumed."))
        progress.events.append(
            self._event(
                "item_used",
                actor_ref="player",
                action_id=action_id,
                data={
                    "kind": "utilize",
                    "mode": "drink",
                    "item_id": item.id,
                    "item_name": item.name,
                    "target_ref": "player",
                    "target_label": player.name,
                    "success": True,
                    "consumed": consumed,
                    "effect": "healing",
                    "healing": applied_healing,
                    "healing_roll_detail": {
                        "dice": f"{dice_count}d{dice_sides}",
                        "dice_total": dice_total,
                        "modifier": modifier,
                        "total": healing_total,
                        "applied_healing": applied_healing,
                    },
                },
            )
        )

    def _resolve_feature_action(
        self,
        player: Actor,
        feature_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        feature_action = player.combat_profile.feature_actions.get(feature_id)
        if feature_action is None:
            progress.messages.append(("system", f"{feature_id} is not implemented yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        if feature_action.economy == "bonus_action" and not self.player_bonus_action_available:
            progress.messages.append(("system", "You have already used your Bonus Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return
        if feature_action.economy == "action" and not self.player_action_available:
            progress.messages.append(("system", "You have already used your Action."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return
        if feature_action.economy == "reaction" and not self.player_reaction_available:
            progress.messages.append(("system", "You have already used your Reaction."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        uses_remaining = player.feature_uses_remaining.get(feature_id, 0)
        if uses_remaining <= 0:
            progress.messages.append(
                ("system", f"You have no uses of {feature_action.label} remaining.")
            )
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        result = resolve_feature_action(player, feature_id, roll_dice)
        if result is None:
            progress.messages.append(("system", f"{feature_action.label} is not implemented yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "feature", "feature_id": feature_id, "success": False},
                )
            )
            return

        if feature_action.economy == "bonus_action":
            self.player_bonus_action_available = False
        elif feature_action.economy == "action":
            self.player_action_available = False
        elif feature_action.economy == "reaction":
            self.player_reaction_available = False

        progress.messages.extend(result.messages)
        healing_effect = next(
            (effect for effect in result.effects if effect.kind == "healing"),
            None,
        )
        healing_data = healing_effect.data if healing_effect is not None else {}
        healing_roll_detail = healing_data.get("roll", {})
        target_ref = healing_effect.target_ref if healing_effect is not None else "player"
        target_label = healing_data.get("target_label", player.name)
        healing = healing_data.get("amount", 0)
        progress.events.append(
            self._event(
                "feature_used",
                actor_ref="player",
                action_id=action_id,
                data={
                    "kind": "feature",
                    "feature_id": result.capability_id,
                    "feature_name": result.capability_name,
                    "target_ref": target_ref,
                    "target_label": target_label,
                    "success": True,
                    "healing": healing,
                    "healing_roll_detail": healing_roll_detail,
                    "uses_remaining": result.resource_updates.get(feature_id),
                    "effects": [
                        {
                            "kind": effect.kind,
                            "target_ref": effect.target_ref,
                            "success": effect.success,
                            "data": effect.data,
                        }
                        for effect in result.effects
                    ],
                },
            )
        )

    def _resolve_spell_action(
        self,
        player: Actor,
        spell_value: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        spellcasting = player.spellcasting
        if spellcasting is None:
            progress.messages.append(("system", "You cannot cast spells."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "spell", "success": False},
                )
            )
            return
        spell_id, target_ref, aim_point = parse_spell_action_value(spell_value)
        spell = next((candidate for candidate in spellcasting.learned_spells if candidate.id == spell_id), None)
        if spell is None:
            progress.messages.append(("system", "That spell is not available."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "spell", "spell_id": spell_id, "success": False},
                )
            )
            return
        cost = self._spell_action_cost(spell)
        block_reason = self._spell_cast_block_reason(spellcasting, spell, cost)
        if block_reason is not None:
            progress.messages.append(("system", block_reason))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "spell", "spell_id": spell.id, "success": False},
                )
            )
            return
        area = self._spell_area(player, spell, target_ref=target_ref, aim_point=aim_point)
        targets = self._spell_area_targets(player, spell, target_ref=target_ref, aim_point=aim_point)
        target = (
            self._spell_target_context(player, target_ref)
            if target_ref is not None
            else targets[0]
            if targets
            else None
        )
        if target is None or not targets:
            progress.messages.append(("system", "That target is not available."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "spell", "spell_id": spell.id, "success": False},
                )
            )
            return
        result = resolve_spell_action(
            SpellActionContext(
                actor=player,
                spell=spell,
                target=target,
                current_round=self.round_number,
                targets=targets,
                area=area,
                source_ref="player",
                roller=roll_die,
            )
        )
        if result is None:
            progress.messages.append(("system", f"{spell.name} is not implemented yet."))
            progress.events.append(
                self._event(
                    "action_resolved",
                    actor_ref="player",
                    action_id=action_id,
                    data={"kind": "spell", "spell_id": spell.id, "success": False},
                )
            )
            return

        self._spend_spell_resources(spellcasting, spell, cost)

        progress.messages.extend(result.messages)
        progress.messages.extend(self._apply_effects(result.effects))
        progress.events.append(
            self._event(
                "spell_cast",
                actor_ref="player",
                action_id=action_id,
                data={
                    "kind": "spell",
                    "spell_id": result.capability_id,
                    "spell_name": result.capability_name,
                    "spell_level": result.details.get("spell_level", spell.level),
                    "target_ref": result.details.get("target_ref", target_ref),
                    "target_label": result.details.get("target_label", target.target_label),
                    "target_refs": result.details.get("target_refs"),
                    "target_labels": result.details.get("target_labels"),
                    "area": result.details.get("area"),
                    "slot_level": result.details.get("slot_level", spell.level),
                    "spell_slots_remaining": (
                        spellcasting.spell_slots_remaining.get(spell.level, 0)
                        if spell.level > 0
                        else None
                    ),
                    "save_detail": result.details.get("save_detail"),
                    "save_details": result.details.get("save_details"),
                    "damage_roll_detail": result.details.get("damage_roll_detail"),
                    "damage_roll_details": result.details.get("damage_roll_details"),
                    "effects": serialize_effects(result.effects),
                    "success": result.details.get("success", False),
                },
            )
        )
        return

    def _spell_target_context(
        self,
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

    def _apply_effects(self, effects) -> list[tuple[str, str]]:
        return apply_effects(
            effects,
            apply_status=self._apply_status,
            remove_status=self._remove_status,
        )

    def _apply_status(self, status: Status) -> None:
        self.conditions = [
            existing
            for existing in self.conditions
            if not (
                existing.target_ref == status.target_ref
                and existing.name == status.name
            )
        ]
        self.conditions.append(status)

    def _remove_status(self, target_ref: ActorRef, status_name: str) -> None:
        self.conditions = [
            existing
            for existing in self.conditions
            if not (
                existing.target_ref == target_ref
                and existing.name == status_name
            )
        ]

    def _apply_player_move(
        self,
        player: Actor,
        direction: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        dx, dy = DIRECTION_DELTAS[direction]
        self.player_position = Position(self.player_position.x + dx, self.player_position.y + dy)
        self.player_movement_remaining = self._player_movement_remaining(player) - 1
        progress.messages.append(
            (
                "system",
                f"You move {direction}. Movement remaining: {self.player_movement_remaining}.",
            )
        )
        progress.events.append(
            self._event(
                "movement_resolved",
                actor_ref="player",
                action_id=action_id,
                data={
                    "direction": direction,
                    "to": {"x": self.player_position.x, "y": self.player_position.y},
                },
            )
        )

    def _queue_player_opportunity_attack(
        self,
        player: Actor,
        enemy_index: int,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: int,
        progress: EncounterProgress,
    ) -> bool:
        if not self._actors_are_opponents("player", _enemy_ref(enemy_index)):
            return False
        if not self.player_reaction_available:
            return False
        if not can_make_opportunity_attack(player, self.item_templates):
            return False
        if not _is_adjacent(from_position, self.player_position):
            return False
        if _is_adjacent(to_position, self.player_position):
            return False

        frame_id = self._next_frame_id()
        trigger_id = self._next_frame_id(prefix="trigger")
        current_frame = self.current_decision()
        self.pending_action = PendingAction(
            id=action_id,
            kind="move",
            actor_ref=_enemy_ref(enemy_index),
            direction=direction,
            from_position=Position(from_position.x, from_position.y),
            to_position=Position(to_position.x, to_position.y),
            resume_enemy_index=enemy_index,
            remaining_movement_after=remaining_movement_after,
            trigger_id=trigger_id,
        )
        self.decision_stack.append(
            DecisionFrame(
                id=frame_id,
                actor_ref="player",
                kind="reaction",
                reason="opportunity_attack",
                parent_frame_id=current_frame.id,
                parent_action_id=action_id,
                can_pass=True,
            )
        )
        progress.events.append(
            self._event(
                "trigger_opened",
                actor_ref="player",
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "kind": "opportunity_attack",
                    "target_ref": _enemy_ref(enemy_index),
                    "trigger_id": trigger_id,
                },
            )
        )
        return True

    def _reaction_actions(self) -> list[EncounterAction]:
        pending_action = self.pending_action
        if pending_action is None or pending_action.kind != "move":
            return [
                EncounterAction(
                    "Pass reaction",
                    "pass",
                    id="player-reaction-pass",
                    actor_ref="player",
                    cost=ActionCost(),
                )
            ]

        target_index = _enemy_index(pending_action.actor_ref)
        target = self.enemies[target_index]
        actions: list[EncounterAction] = []
        if self.player_reaction_available and target.is_alive:
            actions.append(
                EncounterAction(
                    f"Opportunity attack {target.actor.name}",
                    "opportunity_attack",
                    target_index,
                    id=f"player-opportunity-attack-{target_index}",
                    actor_ref="player",
                    source_trigger_id=pending_action.trigger_id,
                    cost=ActionCost(reaction=1),
                )
            )
        actions.append(
            EncounterAction(
                "Pass reaction",
                "pass",
                id="player-reaction-pass",
                actor_ref="player",
                source_trigger_id=pending_action.trigger_id,
            )
        )
        return actions

    def _active_turn_actor(self) -> tuple[str, int | None]:
        self._normalize_turn()
        if self.turn_index == 0:
            return ("player", None)
        return ("enemy", self.turn_index - 1)

    def _actor_controller(self, actor_ref: ActorRef) -> str:
        if self.control_mode == "all-user":
            return "user"
        team_id = self._actor_team_id(actor_ref)
        team = next(
            (team for team in self.definition.teams if team.id == team_id),
            None,
        )
        return team.controller if team is not None else (
            "user" if actor_ref == "player" else "ai"
        )

    def _actor_team_id(self, actor_ref: ActorRef) -> str:
        actor_id = (
            "player"
            if actor_ref == "player"
            else self.enemies[_enemy_index(actor_ref)].actor_id
        )
        team = next(
            (team for team in self.definition.teams if actor_id in team.members),
            None,
        )
        return team.id if team is not None else actor_id

    def _actors_are_opponents(
        self,
        first_actor_ref: ActorRef,
        second_actor_ref: ActorRef,
    ) -> bool:
        return self._actor_team_id(first_actor_ref) != self._actor_team_id(
            second_actor_ref
        )

    def _check_transition(self) -> str | None:
        opponents = [
            enemy
            for index, enemy in enumerate(self.enemies)
            if self._actors_are_opponents("player", _enemy_ref(index))
        ]
        if opponents and all(not enemy.is_alive for enemy in opponents):
            return self.definition.victory.next_scene if self.definition.victory else None
        return None

    def _advance_turn(self) -> None:
        ending_actor_ref = self.current_decision().actor_ref
        ending_round = self.round_number
        self._expire_conditions_for_turn_end(ending_actor_ref, ending_round)
        self.turn_index += 1
        if self.turn_index >= self._turn_count():
            self.turn_index = 0
            self.round_number += 1
        self._normalize_turn()
        if self.turn_index == 0:
            self.player_movement_remaining = None
            self.player_action_available = True
            self.player_attacks_remaining = 0
            self.player_bonus_action_available = True
        else:
            self.enemies[self.turn_index - 1].movement_remaining = None

    def _expire_conditions_for_turn_end(
        self,
        actor_ref: ActorRef,
        round_number: int,
    ) -> None:
        self.conditions = [
            condition
            for condition in self.conditions
            if not (
                condition.expires_on_actor_ref == actor_ref
                and condition.expires_on_round == round_number
            )
        ]

    def _maybe_reset_reactions(self) -> None:
        if self.turn_index != 0:
            return
        self.player_reaction_available = True
        for enemy in self.enemies:
            enemy.reaction_available = True

    def _normalize_turn(self) -> None:
        if self.turn_index >= self._turn_count():
            self.turn_index = 0

        for _ in range(self._turn_count()):
            if self.turn_index == 0:
                return
            enemy = self.enemies[self.turn_index - 1]
            if enemy.is_alive:
                return
            self.turn_index += 1
            if self.turn_index >= self._turn_count():
                self.turn_index = 0
                self.round_number += 1

    def _player_movement_remaining(self, player: Actor) -> int:
        if self.player_movement_remaining is None:
            self.player_movement_remaining = _movement_squares(player)
        return self.player_movement_remaining

    def _turn_count(self) -> int:
        return len(self.enemies) + 1

    def _live_enemy_at(self, x: int, y: int) -> EncounterEnemyState | None:
        return next(
            (
                enemy
                for enemy in self.enemies
                if enemy.is_alive and enemy.position.x == x and enemy.position.y == y
            ),
            None,
        )

    def _is_free_for_enemy(self, x: int, y: int) -> bool:
        if not self._is_within_bounds(x, y):
            return False
        if self.player_position.x == x and self.player_position.y == y:
            return False
        return self._live_enemy_at(x, y) is None

    def _is_within_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.definition.grid.width and 0 <= y < self.definition.grid.height

    def _next_action_id(self) -> str:
        action_id = f"action_{self.action_sequence}"
        self.action_sequence += 1
        return action_id

    def _next_frame_id(self, prefix: str = "frame") -> str:
        frame_id = f"{prefix}_{self.frame_sequence}"
        self.frame_sequence += 1
        return frame_id

    def _event(
        self,
        event_type: str,
        actor_ref: ActorRef | None = None,
        frame_id: str | None = None,
        action_id: str | None = None,
        data: dict[str, object] | None = None,
    ) -> CombatEvent:
        event = CombatEvent(
            seq=self.event_sequence,
            type=event_type,
            actor_ref=actor_ref,
            frame_id=frame_id,
            action_id=action_id,
            data=data or {},
        )
        self.event_sequence += 1
        return event

    def _merge_progress(self, target: EncounterProgress, source: EncounterProgress) -> None:
        target.messages.extend(source.messages)
        target.events.extend(source.events)
        if source.transition is not None:
            target.transition = source.transition
        target.paused_for_decision = target.paused_for_decision or source.paused_for_decision
        target.paused_for_ai = target.paused_for_ai or source.paused_for_ai

    def _export_pending_action(self) -> dict[str, object] | None:
        if self.pending_action is None:
            return None
        return {
            "id": self.pending_action.id,
            "kind": self.pending_action.kind,
            "actor_ref": self.pending_action.actor_ref,
            "direction": self.pending_action.direction,
            "from": {
                "x": self.pending_action.from_position.x,
                "y": self.pending_action.from_position.y,
            },
            "to": {
                "x": self.pending_action.to_position.x,
                "y": self.pending_action.to_position.y,
            },
            "resume_enemy_index": self.pending_action.resume_enemy_index,
            "remaining_movement_after": self.pending_action.remaining_movement_after,
            "trigger_id": self.pending_action.trigger_id,
        }

    def _actor_label(self, actor_ref: ActorRef) -> str:
        if actor_ref == "player":
            return "Player"
        enemy_index = _enemy_index(actor_ref)
        enemy = self.enemies[enemy_index]
        return f"Enemy {enemy_index + 1} ({enemy.actor.name})"

    def _living_actor_refs(self, player: Actor) -> list[ActorRef]:
        refs: list[ActorRef] = []
        if player.get_health() > 0:
            refs.append("player")
        refs.extend(
            _enemy_ref(index)
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
        )
        return refs

    def _actor_position(self, actor_ref: ActorRef) -> Position:
        if actor_ref == "player":
            return self.player_position
        return self.enemies[_enemy_index(actor_ref)].position

    def _actor_for_ref(self, player: Actor, actor_ref: ActorRef) -> Actor:
        if actor_ref == "player":
            return player
        return self.enemies[_enemy_index(actor_ref)].actor

def _attack_roll_mode(
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    if attack_type != "ranged" or attacker_position is None:
        return "normal"
    if any(_is_adjacent(attacker_position, position) for position in nearby_opponent_positions):
        return "disadvantage"
    return "normal"


def _combine_roll_modes(modes: list[D20RollMode]) -> D20RollMode:
    advantages = sum(1 for mode in modes if mode == "advantage")
    disadvantages = sum(1 for mode in modes if mode == "disadvantage")
    if advantages and disadvantages:
        return "normal"
    if advantages:
        return "advantage"
    if disadvantages:
        return "disadvantage"
    return "normal"

def _condition_suffix(conditions: tuple[Status, ...]) -> str:
    if not conditions:
        return ""
    labels = ", ".join(condition.name.capitalize() for condition in conditions)
    return f" [{labels}]"

def _reroll_die_action_id(action_id: str, die_index: int) -> str:
    return f"{action_id}-reroll-damage-{die_index}"


def _enemy_ref(enemy_index: int) -> str:
    return f"enemy:{enemy_index}"


def _enemy_index(actor_ref: ActorRef) -> int:
    prefix = "enemy:"
    if not actor_ref.startswith(prefix):
        raise ValueError(f"'{actor_ref}' is not an enemy actor reference.")
    return int(actor_ref[len(prefix):])
