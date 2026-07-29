from __future__ import annotations

from copy import deepcopy
from typing import Any

from .behaviors import (
    build_behavior as _build_behavior,
    is_adjacent as _is_adjacent,
)
from ..effects.application import apply_effects
from ..effects.results import EffectResult
from .facades import (
    EncounterActions,
    EncounterQueries,
    EncounterReadModel,
    EncounterRules,
)
from .models import (
    ActionCost,
    CreatureRef,
    CombatEvent,
    DecisionFrame,
    EncounterAction,
    Combatant,
    EncounterProgress,
    EncounterStateData,
    InitiativeEntry,
    InterruptState,
    PendingAttack,
    RoundState,
    TurnState,
    TurnResources,
    PendingAction,
)
from .reactions import REACTION_ENGINE, ReactionEngine
from .refs import enemy_index as _enemy_index, enemy_ref as _enemy_ref
from ..creatures import Creature
from ..equipment import Item
from ..geometry import Position
from .definitions import EncounterBehavior, EncounterDefinition
from ..effects.conditions import Status
from ..geometry import GeometryConfig
from ..rolls.dice import D20RollMode, roll_dice as _roll_dice, roll_die as _roll_die
from ..effects.triggered import TriggeredEffect, matching_effects
from .turn_flow import TURN_ENGINE, TurnEngine
from .queries import (
    living_enemy_at as _living_enemy_at_impl,
    player_movement_remaining as _player_movement_remaining_query,
)

# Keep these module-level names for tests and helpers that monkeypatch
# `srd_arena.domain.encounters.encounter.roll_die` / `roll_dice`.
roll_die = _roll_die
roll_dice = _roll_dice
__all__ = ["ActionCost", "EncounterAction", "EncounterState", "roll_die", "roll_dice"]


class EncounterState(EncounterStateData):
    @property
    def player_combatant(self) -> Combatant:
        return self.combatants["player"]

    @property
    def player_position(self) -> Position:
        return self.player_combatant.position

    @player_position.setter
    def player_position(self, value: Position) -> None:
        self.player_combatant.position = value

    @property
    def enemies(self) -> list[Combatant]:
        return [
            combatant
            for actor_ref, combatant in self.combatants.items()
            if actor_ref != "player"
        ]

    def combatant(self, actor_ref: CreatureRef) -> Combatant:
        return self.combatants[actor_ref]

    @property
    def actions(self) -> EncounterActions:
        return EncounterActions(self)

    @property
    def read_model(self) -> EncounterReadModel:
        return EncounterReadModel(self)

    @property
    def queries(self) -> EncounterQueries:
        return EncounterQueries(self)

    @property
    def rules(self) -> EncounterRules:
        return EncounterRules(self)

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
        return self.player_combatant.turn.movement_remaining

    @player_movement_remaining.setter
    def player_movement_remaining(self, value: int | None) -> None:
        self.player_combatant.turn.movement_remaining = value

    @property
    def player_action_available(self) -> bool:
        return self.player_combatant.turn.actions_remaining > 0

    @player_action_available.setter
    def player_action_available(self, value: bool) -> None:
        if value:
            self.player_combatant.turn.actions_remaining = max(
                1, self.player_combatant.turn.actions_remaining
            )
        else:
            self.player_combatant.turn.actions_remaining = 0

    @property
    def player_actions_remaining(self) -> int:
        return self.player_combatant.turn.actions_remaining

    @player_actions_remaining.setter
    def player_actions_remaining(self, value: int) -> None:
        self.player_combatant.turn.actions_remaining = max(0, value)

    @property
    def player_magic_actions_remaining(self) -> int:
        return self.player_combatant.turn.magic_actions_remaining

    @player_magic_actions_remaining.setter
    def player_magic_actions_remaining(self, value: int) -> None:
        self.player_combatant.turn.magic_actions_remaining = max(0, value)

    @property
    def player_attacks_remaining(self) -> int:
        return self.player_combatant.turn.attacks_remaining

    @player_attacks_remaining.setter
    def player_attacks_remaining(self, value: int) -> None:
        self.player_combatant.turn.attacks_remaining = value

    @property
    def player_bonus_action_available(self) -> bool:
        return self.player_combatant.turn.bonus_action_available

    @player_bonus_action_available.setter
    def player_bonus_action_available(self, value: bool) -> None:
        self.player_combatant.turn.bonus_action_available = value

    @property
    def player_reaction_available(self) -> bool:
        return self.player_combatant.turn.reaction_available

    @player_reaction_available.setter
    def player_reaction_available(self, value: bool) -> None:
        self.player_combatant.turn.reaction_available = value

    @classmethod
    def from_definition(
        cls,
        encounter_id: str,
        definition: EncounterDefinition,
        player: Creature,
        creature_templates: dict[str, Creature],
        item_templates: dict[str, Item] | None = None,
        control_mode: str = "default",
        geometry_config: GeometryConfig | None = None,
    ) -> EncounterState:
        player_participants = [
            participant
            for participant in definition.participants
            if participant.actor_id == player.id
        ]
        if len(player_participants) != 1:
            raise ValueError(
                f"Encounter '{definition.id}' must place player '{player.id}' exactly once."
            )
        player_participant = player_participants[0]
        team_by_actor = {
            actor_id: team
            for team in definition.teams
            for actor_id in team.members
        }
        player_team = team_by_actor.get(player.id)
        combatants = {
            "player": Combatant(
                ref="player",
                actor_id=player.id,
                creature=player,
                position=Position(
                    player_participant.start.x,
                    player_participant.start.y,
                ),
                controller="user",
                team_id=player_team.id if player_team is not None else player.id,
                behavior=EncounterBehavior(type="external"),
                turn=TurnResources(),
            )
        }
        for index, participant in enumerate(
            participant
            for participant in definition.participants
            if participant.actor_id != player.id
        ):
            if participant.actor_id == player.id:
                continue
            if participant.behavior is None:
                raise ValueError(
                    f"Encounter '{definition.id}' participant "
                    f"'{participant.actor_id}' requires a behavior."
                )
            actor_ref = _enemy_ref(index)
            team = team_by_actor.get(participant.actor_id)
            combatants[actor_ref] = Combatant(
                    ref=actor_ref,
                    actor_id=participant.actor_id,
                    creature=deepcopy(creature_templates[participant.actor_id]),
                    position=Position(participant.start.x, participant.start.y),
                    controller=(
                        "user"
                        if control_mode == "all-user"
                        else team.controller if team is not None else "ai"
                    ),
                    team_id=team.id if team is not None else participant.actor_id,
                    behavior=deepcopy(participant.behavior),
                )
        state = cls(
            encounter_id=encounter_id,
            definition=definition,
            combatants=combatants,
            control_mode=control_mode,
            round=RoundState(),
            turn=TurnState(),
            interrupts=InterruptState(),
            item_templates=item_templates or {},
            geometry_config=geometry_config or GeometryConfig(),
        )
        state._roll_initiative(player)
        state._initialize_behaviors()
        return state

    def _initialize_behaviors(self) -> None:
        self._behaviors = []
        for enemy in self.enemies:
            behavior = _build_behavior(enemy, self.item_templates)
            next(behavior)
            self._behaviors.append(behavior)

    def _roll_initiative(self, player: Creature) -> None:
        entries = [
            InitiativeEntry(
                actor_ref="player",
                roll=roll_die(20),
                modifier=player.get_modifier(player.attributes.dexterity),
                total=0,
            )
        ]
        for index, enemy in enumerate(self.enemies):
            entries.append(
                InitiativeEntry(
                    actor_ref=_enemy_ref(index),
                    roll=roll_die(20),
                    modifier=enemy.creature.get_modifier(
                        enemy.creature.attributes.dexterity
                    ),
                    total=0,
                )
            )
        for entry in entries:
            entry.total = entry.roll + entry.modifier
        entries.sort(
            key=lambda entry: (
                -entry.total,
                -entry.modifier,
                0 if entry.actor_ref == "player" else 1,
                entry.actor_ref,
            )
        )
        self.initiative_entries = entries
        self.initiative_order = [entry.actor_ref for entry in entries]

    def current_turn_label(self) -> str:
        decision = self.current_decision()
        if decision.kind == "reaction":
            return f"{self._creature_label(decision.actor_ref)} (Reaction)"
        return self._creature_label(decision.actor_ref)

    def current_decision(self) -> DecisionFrame:
        if self.decision_stack:
            return self.decision_stack[-1]
        creature_type, enemy_index = self._active_turn_actor()
        if creature_type == "player":
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

    def conditions_for(self, actor_ref: CreatureRef) -> tuple[Status, ...]:
        return tuple(
            condition
            for condition in self.conditions
            if condition.target_ref == actor_ref
        )

    def has_condition(self, actor_ref: CreatureRef, condition_name: str) -> bool:
        return any(
            condition.name == condition_name
            for condition in self.conditions_for(actor_ref)
        )

    def _attack_roll_mode_for(self, *args: Any) -> D20RollMode:
        if len(args) == 6:
            (
                _player,
                attacker_ref,
                target_ref,
                attack_type,
                attacker_position,
                nearby_opponent_positions,
            ) = args
        elif len(args) == 5:
            (
                attacker_ref,
                target_ref,
                attack_type,
                attacker_position,
                nearby_opponent_positions,
            ) = args
        else:
            raise TypeError(
                "_attack_roll_mode_for expects either "
                "(player, attacker_ref, target_ref, attack_type, attacker_position, nearby_opponent_positions) "
                "or (attacker_ref, target_ref, attack_type, attacker_position, nearby_opponent_positions)."
            )
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
        if any(
            status.name == "grappled"
            and status.target_ref == attacker_ref
            and status.source_ref != target_ref
            for status in self.conditions
        ):
            modes.append("disadvantage")
        for effect in matching_effects(
            self._active_status_effects(),
            "attack_roll_created",
            context,
        ):
            if effect.operation == "grant_advantage":
                modes.append("advantage")
            elif effect.operation == "grant_disadvantage":
                modes.append("disadvantage")
        return _combine_roll_modes(modes)

    def _active_status_effects(self) -> list[TriggeredEffect]:
        return [
            effect for status in self.conditions for effect in status.triggered_effects
        ]

    def active_creature(self) -> tuple[str, int | None]:
        actor_ref = self.current_decision().actor_ref
        if actor_ref == "player":
            return ("player", None)
        return ("enemy", _enemy_index(actor_ref))

    def requires_automatic_advance(self) -> bool:
        return self.rules.controller(self.current_decision().actor_ref) == "ai"


    def _apply_effects(
        self,
        effects: list[EffectResult],
    ) -> list[tuple[str, str]]:
        return apply_effects(
            effects,
            apply_status=self.rules.apply_status,
            remove_status=self.rules.remove_status,
        )


    def _open_damage_reroll_decision(self, **kwargs: Any) -> None:
        self.reaction_engine.open_damage_reroll_decision(self, **kwargs)

    def _reroll_damage_actions(self) -> list[EncounterAction]:
        return self.reaction_engine.reroll_damage_actions(self)

    def _apply_damage_reroll_action(
        self,
        player: Creature,
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
        player: Creature,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        self.reaction_engine.finalize_pending_attack(self, player, progress, decision)

    def _complete_parent_reaction(
        self,
        player: Creature,
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

    def _consume_action(self, *, allow_magic: bool) -> None:
        if self.player_actions_remaining <= 0:
            raise RuntimeError("No Action remains to consume.")
        non_magic_only_actions = max(
            0,
            self.player_actions_remaining - self.player_magic_actions_remaining,
        )
        if allow_magic:
            if self.player_magic_actions_remaining <= 0:
                raise RuntimeError("No spell-capable Action remains to consume.")
            self.player_magic_actions_remaining -= 1
        elif non_magic_only_actions <= 0 and self.player_magic_actions_remaining > 0:
            self.player_magic_actions_remaining -= 1
        self.player_actions_remaining -= 1

    def advance_until_next_decision(self, player: Creature) -> EncounterProgress:
        return self.turn_engine.advance_until_next_decision(self, player)

    def _run_enemy_turn(
        self,
        player: Creature,
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
        player: Creature,
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
        player: Creature,
        progress: EncounterProgress,
    ) -> None:
        self.reaction_engine.resume_pending_action(self, player, progress)

    def _resolve_enemy_opportunity_attacks_against_player(
        self,
        player: Creature,
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
        player: Creature,
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
        actor_ref: CreatureRef,
        round_number: int,
    ) -> None:
        self.turn_engine.expire_conditions_for_turn_end(self, actor_ref, round_number)

    def _maybe_reset_reactions(self) -> None:
        self.turn_engine.maybe_reset_reactions(self)

    def _normalize_turn(self) -> None:
        self.turn_engine.normalize_turn(self)

    def _player_movement_remaining(self, player: Creature) -> int:
        return _player_movement_remaining_query(self, player)

    def _turn_count(self) -> int:
        return self.turn_engine.turn_count(self)

    def _live_enemy_at(self, x: int, y: int) -> Combatant | None:
        return _living_enemy_at_impl(self, x, y)

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
        actor_ref: CreatureRef | None = None,
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

    def _merge_progress(
        self, target: EncounterProgress, source: EncounterProgress
    ) -> None:
        target.messages.extend(source.messages)
        target.events.extend(source.events)
        if source.transition is not None:
            target.transition = source.transition
        target.paused_for_decision = (
            target.paused_for_decision or source.paused_for_decision
        )
        target.paused_for_pacing = target.paused_for_pacing or source.paused_for_pacing


    def _creature_label(self, actor_ref: CreatureRef) -> str:
        if actor_ref == "player":
            return "Player"
        enemy_index = _enemy_index(actor_ref)
        enemy = self.enemies[enemy_index]
        return f"Enemy {enemy_index + 1} ({enemy.creature.name})"

    def _living_creature_refs(self, player: Creature) -> list[CreatureRef]:
        refs: list[CreatureRef] = []
        if player.get_health() > 0:
            refs.append("player")
        refs.extend(
            _enemy_ref(index)
            for index, enemy in enumerate(self.enemies)
            if enemy.is_alive
        )
        return refs

    def _creature_position(self, actor_ref: CreatureRef) -> Position:
        if actor_ref == "player":
            return self.player_position
        return self.enemies[_enemy_index(actor_ref)].position

    def _position_is_free(
        self,
        x: int,
        y: int,
        *,
        ignored_refs: set[CreatureRef] | frozenset[CreatureRef] = frozenset(),
    ) -> bool:
        if (
            x < 0
            or y < 0
            or x >= self.definition.grid.width
            or y >= self.definition.grid.height
        ):
            return False
        if (
            "player" not in ignored_refs
            and self.player_position.x == x
            and self.player_position.y == y
        ):
            return False
        for index, enemy in enumerate(self.enemies):
            actor_ref = _enemy_ref(index)
            if actor_ref in ignored_refs or not enemy.is_alive:
                continue
            if enemy.position.x == x and enemy.position.y == y:
                return False
        return True

    def _creature_size(self, player: Creature, actor_ref: CreatureRef) -> str:
        return self.rules.creature(player, actor_ref).size



def _attack_roll_mode(
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    if attack_type != "ranged" or attacker_position is None:
        return "normal"
    if any(
        _is_adjacent(attacker_position, position)
        for position in nearby_opponent_positions
    ):
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
