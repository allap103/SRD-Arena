from __future__ import annotations

from copy import deepcopy

from .behaviors import (
    build_behavior as _build_behavior,
    is_adjacent as _is_adjacent,
    movement_squares as _movement_squares,
)
from .action_options import (
    available_actions as _available_actions_impl,
    available_feature_actions as _available_feature_actions_impl,
    available_spell_actions as _available_spell_actions_impl,
    feature_action_available as _feature_action_available_impl,
    spell_action_cost as _spell_action_cost_impl,
    spell_action_targets as _spell_action_targets_impl,
    spell_area as _spell_area_impl,
    spell_area_targets as _spell_area_targets_impl,
    spell_cast_block_reason_for as _spell_cast_block_reason_impl,
    spell_range_squares_for as _spell_range_squares_impl,
    spell_target_context as _spell_target_context_impl,
    spell_targets_self_only_for as _spell_targets_self_only_impl,
    spend_spell_resources as _spend_spell_resources_impl,
    targets_in_area as _targets_in_area_impl,
)
from .effects import apply_effects
from .models import (
    ActionCost,
    ActorRef,
    CombatEvent,
    DecisionFrame,
    DecisionFrameSnapshot,
    EncounterAction,
    EncounterEnemyState,
    EncounterProgress,
    EncounterSnapshot,
    EncounterSnapshotEnemy,
    EncounterStateData,
    InterruptState,
    PendingAttack,
    RoundState,
    TurnState,
    PendingAction,
    PendingActionSnapshot,
)
from .pending import restore_pending_attack, snapshot_pending_attack
from .player_actions import (
    apply_action as _apply_action_impl,
    apply_player_move as _apply_player_move_impl,
    apply_user_controlled_enemy_action as _apply_user_controlled_enemy_action_impl,
    resolve_flee_action as _resolve_flee_action_impl,
    resolve_feature_action as _resolve_feature_action_impl,
    resolve_player_attack_action as _resolve_player_attack_action_impl,
    resolve_spell_action as _resolve_spell_action_impl,
    resolve_utilize_action as _resolve_utilize_action_impl,
    resolve_wait_action as _resolve_wait_action_impl,
    user_controlled_enemy_actions as _user_controlled_enemy_actions_impl,
)
from .reactions import REACTION_ENGINE, ReactionEngine
from .refs import enemy_index as _enemy_index, enemy_ref as _enemy_ref
from ..models.actor import Actor
from ..models.item import Item
from ..models.scene import Encounter, Position
from ..models.rules_config import RulesConfig
from ..models.status import Status, StatusSnapshot
from ..rules.registry import matching_rules
from ..rules.types import RuleGrant
from .turn_flow import TURN_ENGINE, TurnEngine
from ..systems.roll import D20RollMode, roll_dice as _roll_dice, roll_die as _roll_die

# Keep these module-level names for tests and helpers that monkeypatch
# `game.combat.encounter.roll_die` / `roll_dice`.
roll_die = _roll_die
roll_dice = _roll_dice
__all__ = ["ActionCost", "EncounterAction", "EncounterState", "roll_die", "roll_dice"]

class EncounterState(EncounterStateData):
    @property
    def reaction_engine(self) -> ReactionEngine:
        return REACTION_ENGINE

    @property
    def turn_engine(self) -> TurnEngine:
        return TURN_ENGINE

    @property
    def decision_stack(self) -> list[DecisionFrame]:
        return self.interrupts.decision_stack

    @decision_stack.setter
    def decision_stack(self, value: list[DecisionFrame]) -> None:
        self.interrupts.decision_stack = value

    @property
    def pending_action(self) -> PendingAction | None:
        return self.interrupts.pending_action

    @pending_action.setter
    def pending_action(self, value: PendingAction | None) -> None:
        self.interrupts.pending_action = value

    @property
    def pending_attack(self) -> PendingAttack | None:
        return self.interrupts.pending_attack

    @pending_attack.setter
    def pending_attack(self, value: PendingAttack | None) -> None:
        self.interrupts.pending_attack = value

    @property
    def turn_index(self) -> int:
        return self.turn.index

    @turn_index.setter
    def turn_index(self, value: int) -> None:
        self.turn.index = value

    @property
    def round_number(self) -> int:
        return self.round.number

    @round_number.setter
    def round_number(self, value: int) -> None:
        self.round.number = value

    @property
    def player_movement_remaining(self) -> int | None:
        return self.turn.player_movement_remaining

    @player_movement_remaining.setter
    def player_movement_remaining(self, value: int | None) -> None:
        self.turn.player_movement_remaining = value

    @property
    def player_action_available(self) -> bool:
        return self.turn.player_action_available

    @player_action_available.setter
    def player_action_available(self, value: bool) -> None:
        self.turn.player_action_available = value

    @property
    def player_attacks_remaining(self) -> int:
        return self.turn.player_attacks_remaining

    @player_attacks_remaining.setter
    def player_attacks_remaining(self, value: int) -> None:
        self.turn.player_attacks_remaining = value

    @property
    def player_bonus_action_available(self) -> bool:
        return self.turn.player_bonus_action_available

    @player_bonus_action_available.setter
    def player_bonus_action_available(self, value: bool) -> None:
        self.turn.player_bonus_action_available = value

    @property
    def player_reaction_available(self) -> bool:
        return self.turn.player_reaction_available

    @player_reaction_available.setter
    def player_reaction_available(self, value: bool) -> None:
        self.turn.player_reaction_available = value

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
            round=RoundState(),
            turn=TurnState(),
            interrupts=InterruptState(),
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
            round=RoundState(number=snapshot.round_number),
            turn=TurnState(
                index=snapshot.turn_index,
                player_movement_remaining=snapshot.player_movement_remaining,
                player_action_available=snapshot.player_action_available,
                player_attacks_remaining=snapshot.player_attacks_remaining,
                player_bonus_action_available=snapshot.player_bonus_action_available,
                player_reaction_available=snapshot.player_reaction_available,
            ),
            action_sequence=snapshot.action_sequence,
            frame_sequence=snapshot.frame_sequence,
            event_sequence=snapshot.event_sequence,
            interrupts=InterruptState(
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
            ),
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

    apply_action = _apply_action_impl
    available_actions = _available_actions_impl
    _available_feature_actions = _available_feature_actions_impl
    _available_spell_actions = _available_spell_actions_impl
    _feature_action_available = _feature_action_available_impl
    _spell_action_cost = _spell_action_cost_impl
    _spell_cast_block_reason = _spell_cast_block_reason_impl
    _spell_targets_self_only = _spell_targets_self_only_impl
    _spell_range_squares = _spell_range_squares_impl
    _spell_action_targets = _spell_action_targets_impl
    _spell_area_targets = _spell_area_targets_impl
    _spend_spell_resources = _spend_spell_resources_impl
    _spell_area = _spell_area_impl
    _targets_in_area = _targets_in_area_impl
    _user_controlled_enemy_actions = _user_controlled_enemy_actions_impl
    _apply_user_controlled_enemy_action = _apply_user_controlled_enemy_action_impl
    _resolve_player_attack_action = _resolve_player_attack_action_impl
    _resolve_wait_action = _resolve_wait_action_impl
    _resolve_flee_action = _resolve_flee_action_impl
    _resolve_utilize_action = _resolve_utilize_action_impl
    _resolve_feature_action = _resolve_feature_action_impl
    _resolve_spell_action = _resolve_spell_action_impl
    _apply_player_move = _apply_player_move_impl

    _spell_target_context = _spell_target_context_impl

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

    def _open_damage_reroll_decision(self, **kwargs) -> None:
        self.reaction_engine.open_damage_reroll_decision(self, **kwargs)

    def _reroll_damage_actions(self) -> list[EncounterAction]:
        return self.reaction_engine.reroll_damage_actions(self)

    def _apply_damage_reroll_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        return self.reaction_engine.apply_damage_reroll_action(
            self,
            player,
            action,
            decision,
        )

    def _finalize_pending_attack(
        self,
        player: Actor,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        self.reaction_engine.finalize_pending_attack(self, player, progress, decision)

    def _complete_parent_reaction(
        self,
        player: Actor,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        self.reaction_engine.complete_parent_reaction(
            self,
            player,
            progress,
            action_id,
        )

    def _pending_attack_event_data(self) -> dict[str, object]:
        return self.reaction_engine.pending_attack_event_data(self)

    def advance_until_next_decision(self, player: Actor) -> EncounterProgress:
        return self.turn_engine.advance_until_next_decision(self, player)

    def _run_enemy_turn(
        self,
        player: Actor,
        enemy_index: int,
        *,
        action_limit: int | None = None,
    ) -> tuple[bool, EncounterProgress, int]:
        return self.turn_engine.run_enemy_turn(
            self,
            player,
            enemy_index,
            action_limit=action_limit,
        )

    def _apply_reaction_action(
        self,
        player: Actor,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        return self.reaction_engine.apply_reaction_action(
            self,
            player,
            action,
            decision,
        )

    def _resume_pending_action(
        self,
        player: Actor,
        progress: EncounterProgress,
    ) -> None:
        self.reaction_engine.resume_pending_action(self, player, progress)

    def _resolve_enemy_opportunity_attacks_against_player(
        self,
        player: Actor,
        direction: str,
        action_id: str,
        progress: EncounterProgress,
    ) -> list[tuple[str, str]]:
        return self.reaction_engine.resolve_enemy_opportunity_attacks_against_player(
            self,
            player,
            direction,
            action_id,
            progress,
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
        return self.reaction_engine.queue_player_opportunity_attack(
            self,
            player,
            enemy_index,
            action_id,
            direction,
            from_position,
            to_position,
            remaining_movement_after,
            progress,
        )

    def _reaction_actions(self) -> list[EncounterAction]:
        return self.reaction_engine.reaction_actions(self)

    def _active_turn_actor(self) -> tuple[str, int | None]:
        return self.turn_engine.active_turn_actor(self)

    def _check_transition(self) -> str | None:
        return self.turn_engine.check_transition(self)

    def _advance_turn(self) -> None:
        self.turn_engine.advance_turn(self)

    def _expire_conditions_for_turn_end(
        self,
        actor_ref: ActorRef,
        round_number: int,
    ) -> None:
        self.turn_engine.expire_conditions_for_turn_end(self, actor_ref, round_number)

    def _maybe_reset_reactions(self) -> None:
        self.turn_engine.maybe_reset_reactions(self)

    def _normalize_turn(self) -> None:
        self.turn_engine.normalize_turn(self)

    def _player_movement_remaining(self, player: Actor) -> int:
        return self.turn_engine.player_movement_remaining(self, player)

    def _turn_count(self) -> int:
        return self.turn_engine.turn_count(self)

    def _live_enemy_at(self, x: int, y: int) -> EncounterEnemyState | None:
        return self.turn_engine.live_enemy_at(self, x, y)

    def _is_free_for_enemy(self, x: int, y: int) -> bool:
        return self.turn_engine.is_free_for_enemy(self, x, y)

    def _is_within_bounds(self, x: int, y: int) -> bool:
        return self.turn_engine.is_within_bounds(self, x, y)

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
