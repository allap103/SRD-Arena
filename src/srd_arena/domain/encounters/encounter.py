from __future__ import annotations

from copy import deepcopy

from .behaviors import (
    build_behavior as _build_behavior,
    is_adjacent as _is_adjacent,
)
from .actions.options import (
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
from ..effects.application import apply_effects
from .serialization import (
    export_decision as _export_decision_impl,
    export_pending_action as _export_pending_action_impl,
    export_state as _export_state_impl,
)
from .models import (
    ActionCost,
    CreatureRef,
    CombatEvent,
    DecisionFrame,
    EncounterAction,
    EncounterCreatureState,
    EncounterProgress,
    EncounterStateData,
    InitiativeEntry,
    InterruptState,
    PendingAttack,
    RoundState,
    TurnState,
    PendingAction,
)
from .actions.player import (
    apply_action as _apply_action_impl,
    apply_creature_action as _apply_creature_action_impl,
    resolve_grapple_action as _resolve_grapple_action_impl,
    resolve_feature_action as _resolve_feature_action_impl,
    resolve_spell_action as _resolve_spell_action_impl,
    resolve_utilize_action as _resolve_utilize_action_impl,
    available_creature_actions as _available_creature_actions_impl,
)
from .reactions import REACTION_ENGINE, ReactionEngine
from .refs import participant_ref as _participant_ref
from ..creatures import Creature
from ..equipment import Item
from ..geometry import Position
from .definitions import EncounterBehavior, EncounterDefinition
from ..effects.conditions import Status
from ..geometry import GeometryConfig
from ..rolls.dice import D20RollMode, roll_dice as _roll_dice, roll_die as _roll_die
from ..effects.triggered import TriggeredEffect, matching_effects
from .turn_flow import TURN_ENGINE, TurnEngine
from .conditions import (
    apply_status as _apply_status_impl,
    condition_sources_for as _condition_sources_for_impl,
    grappled_sources_for as _grappled_sources_for_impl,
    grappling_targets_for as _grappling_targets_for_impl,
    is_grappled as _is_grappled_impl,
    movement_cost_for as _movement_cost_for_impl,
    remove_status as _remove_status_impl,
    status_replaces as _status_replaces_impl,
)
from .participants import (
    creatures_are_opponents as _creatures_are_opponents_impl,
    creature_controller as _creature_controller_impl,
    creature_for_ref as _creature_for_ref_impl,
    creature_team_id as _creature_team_id_impl,
)
from .queries import (
    living_non_primary_creature_at as _living_non_primary_creature_at_impl,
    active_movement_remaining as _active_movement_remaining_query,
)

# Keep these module-level names for tests and helpers that monkeypatch
# `srd_arena.domain.encounters.encounter.roll_die` / `roll_dice`.
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
    def primary_creature_state(self) -> EncounterCreatureState:
        return self.creatures[self.primary_creature_ref]

    @property
    def active_creature_state(self) -> EncounterCreatureState:
        return self.creatures[self.current_decision().creature_ref]

    @property
    def primary_position(self) -> Position:
        return self.primary_creature_state.position

    @primary_position.setter
    def primary_position(self, value: Position) -> None:
        self.primary_creature_state.position = value

    @property
    def active_movement_remaining(self) -> int | None:
        return self.active_creature_state.movement_remaining

    @active_movement_remaining.setter
    def active_movement_remaining(self, value: int | None) -> None:
        self.active_creature_state.movement_remaining = value

    @property
    def active_action_available(self) -> bool:
        return self.active_creature_state.actions_remaining > 0

    @active_action_available.setter
    def active_action_available(self, value: bool) -> None:
        if value:
            self.active_creature_state.actions_remaining = max(
                1,
                self.active_creature_state.actions_remaining,
            )
        else:
            self.active_creature_state.actions_remaining = 0

    @property
    def active_actions_remaining(self) -> int:
        return self.active_creature_state.actions_remaining

    @active_actions_remaining.setter
    def active_actions_remaining(self, value: int) -> None:
        self.active_creature_state.actions_remaining = max(0, value)

    @property
    def active_magic_actions_remaining(self) -> int:
        return self.active_creature_state.magic_actions_remaining

    @active_magic_actions_remaining.setter
    def active_magic_actions_remaining(self, value: int) -> None:
        self.active_creature_state.magic_actions_remaining = max(0, value)

    @property
    def active_attacks_remaining(self) -> int:
        return self.active_creature_state.attacks_remaining

    @active_attacks_remaining.setter
    def active_attacks_remaining(self, value: int) -> None:
        self.active_creature_state.attacks_remaining = value

    @property
    def active_bonus_action_available(self) -> bool:
        return self.active_creature_state.bonus_action_available

    @active_bonus_action_available.setter
    def active_bonus_action_available(self, value: bool) -> None:
        self.active_creature_state.bonus_action_available = value

    @property
    def active_reaction_available(self) -> bool:
        return self.active_creature_state.reaction_available

    @active_reaction_available.setter
    def active_reaction_available(self, value: bool) -> None:
        self.active_creature_state.reaction_available = value

    @classmethod
    def from_definition(
        cls,
        encounter_id: str,
        definition: EncounterDefinition,
        player: Creature,
        creature_templates: dict[str, Creature],
        item_templates: dict[str, Item] | None = None,
        control_mode: str = "default",
        controllers_by_creature: dict[str, str] | None = None,
        geometry_config: GeometryConfig | None = None,
    ) -> EncounterState:
        player_participants = [
            participant
            for participant in definition.participants
            if participant.creature_id == player.id
        ]
        if len(player_participants) != 1:
            raise ValueError(
                f"Encounter '{definition.id}' must place player '{player.id}' exactly once."
            )
        player_participant = player_participants[0]
        creatures = {
            "player": EncounterCreatureState(
                creature_id=player.id,
                creature=player,
                position=Position(
                    player_participant.start.x,
                    player_participant.start.y,
                ),
                behavior=deepcopy(
                    player_participant.behavior or EncounterBehavior(type="wait")
                ),
            )
        }
        participant_index = 0
        for participant in definition.participants:
            if participant.creature_id == player.id:
                continue
            creatures[_participant_ref(participant_index)] = EncounterCreatureState(
                creature_id=participant.creature_id,
                creature=deepcopy(creature_templates[participant.creature_id]),
                position=Position(participant.start.x, participant.start.y),
                behavior=deepcopy(
                    participant.behavior or EncounterBehavior(type="wait")
                ),
            )
            participant_index += 1
        state = cls(
            encounter_id=encounter_id,
            definition=definition,
            creatures=creatures,
            control_mode=control_mode,
            controllers_by_creature=dict(controllers_by_creature or {}),
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
        self._behaviors = {}
        for creature_ref, creature_state in self.creatures.items():
            behavior = _build_behavior(creature_state, self.item_templates)
            next(behavior)
            self._behaviors[creature_ref] = behavior

    def _roll_initiative(self, _player: Creature) -> None:
        entries = [
            InitiativeEntry(
                creature_ref=creature_ref,
                roll=roll_die(20),
                modifier=creature_state.creature.get_modifier(
                    creature_state.creature.attributes.dexterity
                ),
                total=0,
            )
            for creature_ref, creature_state in self.creatures.items()
        ]
        for entry in entries:
            entry.total = entry.roll + entry.modifier
        entries.sort(
            key=lambda entry: (
                -entry.total,
                -entry.modifier,
                0 if entry.creature_ref == self.primary_creature_ref else 1,
                entry.creature_ref,
            )
        )
        self.initiative_entries = entries
        self.initiative_order = [entry.creature_ref for entry in entries]

    def current_turn_label(self) -> str:
        decision = self.current_decision()
        if decision.kind == "reaction":
            return f"{self._creature_label(decision.creature_ref)} (Reaction)"
        return self._creature_label(decision.creature_ref)

    def current_decision(self) -> DecisionFrame:
        if self.decision_stack:
            return self.decision_stack[-1]
        creature_ref = self._active_turn_creature()
        return DecisionFrame(
            id=f"turn-{creature_ref.replace(':', '-')}",
            creature_ref=creature_ref,
            kind="turn",
            reason="normal_turn",
        )

    def conditions_for(self, creature_ref: CreatureRef) -> tuple[Status, ...]:
        return tuple(condition for condition in self.conditions if condition.target_ref == creature_ref)

    def has_condition(self, creature_ref: CreatureRef, condition_name: str) -> bool:
        return any(
            condition.name == condition_name
            for condition in self.conditions_for(creature_ref)
        )

    def _attack_roll_mode_for(self, *args) -> D20RollMode:
        if len(args) == 6:
            _player, attacker_ref, target_ref, attack_type, attacker_position, nearby_opponent_positions = args
        elif len(args) == 5:
            attacker_ref, target_ref, attack_type, attacker_position, nearby_opponent_positions = args
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
            effect
            for status in self.conditions
            for effect in status.triggered_effects
        ]

    def active_creature(self) -> CreatureRef:
        return self.current_decision().creature_ref

    def needs_ai_advance(self) -> bool:
        return self._creature_controller(self.current_decision().creature_ref) == "ai"

    apply_action = _apply_action_impl
    export_decision = _export_decision_impl
    export_state = _export_state_impl
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
    _available_creature_actions = _available_creature_actions_impl
    _apply_creature_action = _apply_creature_action_impl
    _resolve_utilize_action = _resolve_utilize_action_impl
    _resolve_feature_action = _resolve_feature_action_impl
    _resolve_spell_action = _resolve_spell_action_impl
    _resolve_grapple_action = _resolve_grapple_action_impl

    _spell_target_context = _spell_target_context_impl

    def _apply_effects(self, effects) -> list[tuple[str, str]]:
        return apply_effects(
            effects,
            apply_status=self._apply_status,
            remove_status=self._remove_status,
        )

    _apply_status = _apply_status_impl
    _remove_status = _remove_status_impl
    _creature_controller = _creature_controller_impl
    _creature_team_id = _creature_team_id_impl
    _creatures_are_opponents = _creatures_are_opponents_impl

    def _open_damage_reroll_decision(self, **kwargs) -> None:
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
        if self.active_actions_remaining <= 0:
            raise RuntimeError("No Action remains to consume.")
        non_magic_only_actions = max(
            0,
            self.active_actions_remaining - self.active_magic_actions_remaining,
        )
        if allow_magic:
            if self.active_magic_actions_remaining <= 0:
                raise RuntimeError("No spell-capable Action remains to consume.")
            self.active_magic_actions_remaining -= 1
        elif non_magic_only_actions <= 0 and self.active_magic_actions_remaining > 0:
            self.active_magic_actions_remaining -= 1
        self.active_actions_remaining -= 1

    def advance_until_next_decision(self, player: Creature) -> EncounterProgress:
        return self.turn_engine.advance_until_next_decision(self, player)

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

    def _reaction_actions(self) -> list[EncounterAction]:
        return self.reaction_engine.reaction_actions(self)

    def _active_turn_creature(self) -> CreatureRef:
        return self.turn_engine.active_turn_creature(self)

    def _check_transition(self) -> str | None:
        return self.turn_engine.check_transition(self)

    def _advance_turn(self) -> None:
        self.turn_engine.advance_turn(self)

    def _expire_conditions_for_turn_end(
        self,
        creature_ref: CreatureRef,
        round_number: int,
    ) -> None:
        self.turn_engine.expire_conditions_for_turn_end(self, creature_ref, round_number)

    def _maybe_reset_reactions(self) -> None:
        self.turn_engine.maybe_reset_reactions(self)

    def _normalize_turn(self) -> None:
        self.turn_engine.normalize_turn(self)

    def _active_movement_remaining(self, player: Creature) -> int:
        return self.active_movement_remaining_for(player)

    active_movement_remaining_for = _active_movement_remaining_query

    def _turn_count(self) -> int:
        return self.turn_engine.turn_count(self)

    living_non_primary_creature_at = _living_non_primary_creature_at_impl

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
        creature_ref: CreatureRef | None = None,
        frame_id: str | None = None,
        action_id: str | None = None,
        data: dict[str, object] | None = None,
    ) -> CombatEvent:
        event = CombatEvent(
            seq=self.event_sequence,
            type=event_type,
            creature_ref=creature_ref,
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

    _export_pending_action = _export_pending_action_impl

    def _creature_label(self, creature_ref: CreatureRef) -> str:
        creature_state = self.creatures[creature_ref]
        return (
            f"{creature_state.creature.name} "
            f"({creature_state.creature_id})"
        )

    def _living_creature_refs(self, player: Creature) -> list[CreatureRef]:
        return [
            creature_ref
            for creature_ref, creature_state in self.creatures.items()
            if creature_state.is_alive
        ]

    def _creature_position(self, creature_ref: CreatureRef) -> Position:
        return self.creatures[creature_ref].position

    def _position_is_free(
        self,
        x: int,
        y: int,
        *,
        ignored_refs: set[CreatureRef] | frozenset[CreatureRef] = frozenset(),
    ) -> bool:
        if x < 0 or y < 0 or x >= self.definition.grid.width or y >= self.definition.grid.height:
            return False
        for creature_ref, creature_state in self.creatures.items():
            if creature_ref in ignored_refs or not creature_state.is_alive:
                continue
            if creature_state.position.x == x and creature_state.position.y == y:
                return False
        return True

    def _creature_size(self, player: Creature, creature_ref: CreatureRef) -> str:
        return self.creatures[creature_ref].creature.size

    _condition_sources_for = _condition_sources_for_impl
    _grappled_sources_for = _grappled_sources_for_impl
    _grappling_targets_for = _grappling_targets_for_impl
    _is_grappled = _is_grappled_impl
    _movement_cost_for = _movement_cost_for_impl
    _creature_for_ref = _creature_for_ref_impl
    _status_replaces = staticmethod(_status_replaces_impl)

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
