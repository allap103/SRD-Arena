from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from .models import (
    DecisionFrameSnapshot,
    DecisionFrame,
    EncounterEnemyState,
    EncounterSnapshot,
    EncounterSnapshotEnemy,
    InitiativeEntrySnapshot,
    InitiativeEntry,
    InterruptState,
    PendingAction,
    PendingActionSnapshot,
    RoundState,
    TurnState,
)
from .pending import restore_pending_attack, snapshot_pending_attack
from .refs import enemy_ref
from ..creatures import Creature
from ..item import Item
from ..config import RulesConfig
from ..geometry import Position
from .definitions import EncounterDefinition
from ..effects.conditions import Status, StatusSnapshot

if TYPE_CHECKING:
    from .encounter import EncounterState


def restore_snapshot(
    state_type: type[EncounterState],
    definition: EncounterDefinition,
    snapshot: EncounterSnapshot,
    creature_templates: dict[str, Creature],
    item_templates: dict[str, Item] | None = None,
    rules_config: RulesConfig | None = None,
) -> EncounterState:
    behavior_by_actor_id = {
        participant.actor_id: participant.behavior
        for participant in definition.participants
        if participant.behavior is not None
    }
    enemies = []
    for index, saved_enemy in enumerate(snapshot.enemies):
        creature = deepcopy(creature_templates[saved_enemy.actor_id])
        creature.current_health = saved_enemy.current_health
        enemies.append(
            EncounterEnemyState(
                actor_id=saved_enemy.actor_id,
                creature=creature,
                position=Position(saved_enemy.position.x, saved_enemy.position.y),
                behavior=deepcopy(behavior_by_actor_id[saved_enemy.actor_id]),
                patrol_index=saved_enemy.patrol_index,
                reaction_available=saved_enemy.reaction_available,
                movement_remaining=saved_enemy.movement_remaining,
            )
        )
    state = state_type(
        encounter_id=snapshot.encounter_id,
        definition=definition,
        player_position=Position(snapshot.player_position.x, snapshot.player_position.y),
        enemies=enemies,
        control_mode=snapshot.control_mode,
        round=RoundState(number=snapshot.round_number),
        turn=TurnState(
            index=snapshot.turn_index,
            player_movement_remaining=snapshot.player_movement_remaining,
            player_actions_remaining=snapshot.player_actions_remaining,
            player_magic_actions_remaining=snapshot.player_magic_actions_remaining,
            player_attacks_remaining=snapshot.player_attacks_remaining,
            player_bonus_action_available=snapshot.player_bonus_action_available,
            player_reaction_available=snapshot.player_reaction_available,
        ),
        action_sequence=snapshot.action_sequence,
        frame_sequence=snapshot.frame_sequence,
        event_sequence=snapshot.event_sequence,
        initiative_order=list(snapshot.initiative_order),
        initiative_entries=[
            InitiativeEntry(
                actor_ref=entry.actor_ref,
                roll=entry.roll,
                modifier=entry.modifier,
                total=entry.total,
            )
            for entry in snapshot.initiative_entries
        ],
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
                expires_on_creature_ref=condition.expires_on_creature_ref,
                expires_on_round=condition.expires_on_round,
            )
            for condition in snapshot.conditions
        ],
        item_templates=item_templates or {},
        rules_config=rules_config or RulesConfig(),
    )
    if not state.initiative_order or len(state.initiative_order) != len(state.enemies) + 1:
        state.initiative_order = [
            "player",
            *(enemy_ref(index) for index, _enemy in enumerate(state.enemies)),
        ]
    if not state.initiative_entries:
        state.initiative_entries = [
            InitiativeEntry(actor_ref=actor_ref, roll=0, modifier=0, total=0)
            for actor_ref in state.initiative_order
        ]
    state._initialize_behaviors()
    state._normalize_turn()
    return state


def create_snapshot(state: EncounterState) -> EncounterSnapshot:
    return EncounterSnapshot(
        encounter_id=state.encounter_id,
        player_position=Position(state.player_position.x, state.player_position.y),
        control_mode=state.control_mode,
        turn_index=state.turn_index,
        round_number=state.round_number,
        player_movement_remaining=state.player_movement_remaining,
        player_actions_remaining=state.player_actions_remaining,
        player_magic_actions_remaining=state.player_magic_actions_remaining,
        player_action_available=state.player_action_available,
        player_attacks_remaining=state.player_attacks_remaining,
        player_bonus_action_available=state.player_bonus_action_available,
        player_reaction_available=state.player_reaction_available,
        action_sequence=state.action_sequence,
        frame_sequence=state.frame_sequence,
        event_sequence=state.event_sequence,
        initiative_order=list(state.initiative_order),
        initiative_entries=[
            InitiativeEntrySnapshot(
                actor_ref=entry.actor_ref,
                roll=entry.roll,
                modifier=entry.modifier,
                total=entry.total,
            )
            for entry in state.initiative_entries
        ],
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
            for frame in state.decision_stack
        ],
        pending_action=(
            PendingActionSnapshot(
                id=state.pending_action.id,
                kind=state.pending_action.kind,
                actor_ref=state.pending_action.actor_ref,
                direction=state.pending_action.direction,
                from_position=Position(
                    state.pending_action.from_position.x,
                    state.pending_action.from_position.y,
                ),
                to_position=Position(
                    state.pending_action.to_position.x,
                    state.pending_action.to_position.y,
                ),
                resume_enemy_index=state.pending_action.resume_enemy_index,
                remaining_movement_after=state.pending_action.remaining_movement_after,
                trigger_id=state.pending_action.trigger_id,
            )
            if state.pending_action is not None
            else None
        ),
        pending_attack=snapshot_pending_attack(state.pending_attack),
        conditions=[
            StatusSnapshot(
                id=condition.id,
                name=condition.name,
                source_ref=condition.source_ref,
                source_label=condition.source_label,
                target_ref=condition.target_ref,
                expires_on_creature_ref=condition.expires_on_creature_ref,
                expires_on_round=condition.expires_on_round,
            )
            for condition in state.conditions
        ],
        enemies=[
            EncounterSnapshotEnemy(
                actor_id=enemy.actor_id,
                current_health=enemy.creature.get_health(),
                position=Position(enemy.position.x, enemy.position.y),
                patrol_index=enemy.patrol_index,
                reaction_available=enemy.reaction_available,
                movement_remaining=enemy.movement_remaining,
            )
            for enemy in state.enemies
        ],
    )
