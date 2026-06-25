from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from .choice_resolver import ChoiceResolver
from .encounter import (
    DecisionFrameSnapshot,
    EncounterSnapshot,
    EncounterSnapshotEnemy,
    PendingActionSnapshot,
)
from .engine import Game
from .models.actor import Actor
from .models.attributes import Attributes, Movement
from .models.scene import Position
from .session import GameSession
from .systems.equipment import Equipment
from .systems.inventory import Inventory

SAVE_VERSION = 2
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
SAVEGAME_EXAMPLE: dict[str, JsonValue] = {
    "version": 2,
    "current_scene_id": "welcome",
    "start_scene_id": "welcome",
    "player": {
        "actor_id": "player",
        "current_health": 12,
        "inventory": ["potion", "dagger"],
        "equipment": {
            "body": "chainmail",
            "right_hand": "dagger",
        },
        "attributes": {
            "base_health": 10,
            "level": 1,
            "strength": 16,
            "dexterity": 12,
            "constitution": 14,
            "wisdom": 8,
            "intelligence": 12,
            "charisma": 10,
            "base_armor_class": 10,
        },
    },
    "completed_tests": [],
}


class AttributeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_health: int
    level: int
    movement: "MovementState" = Field(default_factory=lambda: MovementState())
    strength: int
    dexterity: int
    constitution: int
    wisdom: int
    intelligence: int
    charisma: int
    base_armor_class: int


class MovementState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed_feet: int = 30
    feet_per_square: int = 5


class PlayerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    current_health: int
    inventory: list[str] = Field(default_factory=list)
    equipment: dict[str, str | None] = Field(default_factory=dict)
    attributes: AttributeState


class CompletedTestState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    choice_text: str


class PositionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class EncounterEnemyStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    current_health: int
    position: PositionState
    patrol_index: int = 0
    reaction_available: bool = True


class DecisionFrameStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    actor_ref: str
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


class PendingActionStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    actor_ref: str
    direction: str
    from_position: PositionState
    to_position: PositionState
    resume_enemy_index: int | None = None
    remaining_movement_after: int | None = None
    trigger_id: str | None = None


class EncounterStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    player_position: PositionState
    turn_index: int = 0
    round_number: int = 1
    player_movement_remaining: int | None = None
    player_action_available: bool = True
    player_attacks_remaining: int = 0
    player_bonus_action_available: bool = True
    player_reaction_available: bool = True
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    decision_stack: list[DecisionFrameStateModel] = Field(default_factory=list)
    pending_action: PendingActionStateModel | None = None
    enemies: list[EncounterEnemyStateModel] = Field(default_factory=list)


class SaveGame(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": SAVEGAME_EXAMPLE},
    )

    version: int = SAVE_VERSION
    current_scene_id: str
    start_scene_id: str = "welcome"
    player: PlayerState
    completed_tests: list[CompletedTestState] = Field(default_factory=list)
    encounter: EncounterStateModel | None = None


def create_save(session: GameSession) -> SaveGame:
    return SaveGame(
        current_scene_id=session.current_scene_id,
        start_scene_id=session.start_scene_id,
        player=_create_player_state(session.player),
        completed_tests=[
            CompletedTestState(scene_id=scene_id, choice_text=choice_text)
            for scene_id, choice_text in sorted(session.choice_resolver.completed_tests)
        ],
        encounter=_create_encounter_state(session.get_encounter_snapshot()),
    )


def restore_save(save: SaveGame, game_dir: str | Path) -> GameSession:
    if save.version != SAVE_VERSION:
        raise ValueError(f"Unsupported save version: {save.version}")

    game = Game(str(game_dir), start_scene=save.start_scene_id)
    session = game.create_session(player_actor_id=save.player.actor_id)

    if save.current_scene_id not in session.scenes:
        raise ValueError(f"Saved scene '{save.current_scene_id}' does not exist.")

    session.player = _restore_player_state(session.player, save.player)
    session.choice_resolver = ChoiceResolver(
        completed_tests={
            (test.scene_id, test.choice_text) for test in save.completed_tests
        }
    )
    session.current_scene_id = save.current_scene_id
    session.restore_encounter_snapshot(_restore_encounter_state(save.encounter))
    return session


def save_to_file(session: GameSession, path: str | Path) -> Path:
    save = create_save(session)
    output_path = Path(path)
    _write_json_atomically(output_path, save.model_dump(mode="json"))
    return output_path


def load_from_file(path: str | Path, game_dir: str | Path) -> GameSession:
    save_path = Path(path)
    with save_path.open("r", encoding="utf-8") as save_file:
        save = SaveGame.model_validate_json(save_file.read())
    return restore_save(save, game_dir)


def get_slot_path(save_dir: str | Path, slot: str | int) -> Path:
    return Path(save_dir) / f"slot_{slot}.json"


def save_to_slot(session: GameSession, save_dir: str | Path, slot: str | int) -> Path:
    return save_to_file(session, get_slot_path(save_dir, slot))


def load_from_slot(
    save_dir: str | Path,
    slot: str | int,
    game_dir: str | Path,
) -> GameSession:
    return load_from_file(get_slot_path(save_dir, slot), game_dir)


def _create_player_state(player: Actor) -> PlayerState:
    return PlayerState(
        actor_id=player.id,
        current_health=player.get_health(),
        inventory=list(player.inventory.items),
        equipment=dict(player.equipment.equipped_items),
        attributes=AttributeState(
            base_health=player.attributes.base_health,
            level=player.attributes.level,
            movement=MovementState(
                speed_feet=player.attributes.movement.speed_feet,
                feet_per_square=player.attributes.movement.feet_per_square,
            ),
            strength=player.attributes.strength,
            dexterity=player.attributes.dexterity,
            constitution=player.attributes.constitution,
            wisdom=player.attributes.wisdom,
            intelligence=player.attributes.intelligence,
            charisma=player.attributes.charisma,
            base_armor_class=player.attributes.base_armor_class,
        ),
    )


def _restore_player_state(player_template: Actor, state: PlayerState) -> Actor:
    return Actor(
        id=player_template.id,
        name=player_template.name,
        description=player_template.description,
        inventory=Inventory(items=list(state.inventory)),
        attributes=Attributes(
            **state.attributes.model_dump(exclude={"movement"}),
            movement=Movement(**state.attributes.movement.model_dump()),
        ),
        equipment=Equipment(equipped_items=dict(state.equipment)),
        current_health=state.current_health,
        class_ref=deepcopy(player_template.class_ref),
        feature_grants=deepcopy(player_template.feature_grants),
        combat_profile=deepcopy(player_template.combat_profile),
        feature_uses_remaining=dict(player_template.feature_uses_remaining),
    )


def _create_encounter_state(snapshot: EncounterSnapshot | None) -> EncounterStateModel | None:
    if snapshot is None:
        return None

    return EncounterStateModel(
        scene_id=snapshot.scene_id,
        player_position=PositionState(
            x=snapshot.player_position.x,
            y=snapshot.player_position.y,
        ),
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
            DecisionFrameStateModel(
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
            PendingActionStateModel(
                id=snapshot.pending_action.id,
                kind=snapshot.pending_action.kind,
                actor_ref=snapshot.pending_action.actor_ref,
                direction=snapshot.pending_action.direction,
                from_position=PositionState(
                    x=snapshot.pending_action.from_position.x,
                    y=snapshot.pending_action.from_position.y,
                ),
                to_position=PositionState(
                    x=snapshot.pending_action.to_position.x,
                    y=snapshot.pending_action.to_position.y,
                ),
                resume_enemy_index=snapshot.pending_action.resume_enemy_index,
                remaining_movement_after=snapshot.pending_action.remaining_movement_after,
                trigger_id=snapshot.pending_action.trigger_id,
            )
            if snapshot.pending_action is not None
            else None
        ),
        enemies=[
            EncounterEnemyStateModel(
                actor_id=enemy.actor_id,
                current_health=enemy.current_health,
                position=PositionState(x=enemy.position.x, y=enemy.position.y),
                patrol_index=enemy.patrol_index,
                reaction_available=enemy.reaction_available,
            )
            for enemy in snapshot.enemies
        ],
    )


def _restore_encounter_state(
    state: EncounterStateModel | None,
) -> EncounterSnapshot | None:
    if state is None:
        return None

    return EncounterSnapshot(
        scene_id=state.scene_id,
        player_position=Position(x=state.player_position.x, y=state.player_position.y),
        turn_index=state.turn_index,
        round_number=state.round_number,
        player_movement_remaining=state.player_movement_remaining,
        player_action_available=state.player_action_available,
        player_attacks_remaining=state.player_attacks_remaining,
        player_bonus_action_available=state.player_bonus_action_available,
        player_reaction_available=state.player_reaction_available,
        action_sequence=state.action_sequence,
        frame_sequence=state.frame_sequence,
        event_sequence=state.event_sequence,
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
                    x=state.pending_action.from_position.x,
                    y=state.pending_action.from_position.y,
                ),
                to_position=Position(
                    x=state.pending_action.to_position.x,
                    y=state.pending_action.to_position.y,
                ),
                resume_enemy_index=state.pending_action.resume_enemy_index,
                remaining_movement_after=state.pending_action.remaining_movement_after,
                trigger_id=state.pending_action.trigger_id,
            )
            if state.pending_action is not None
            else None
        ),
        enemies=[
            EncounterSnapshotEnemy(
                actor_id=enemy.actor_id,
                current_health=enemy.current_health,
                position=Position(x=enemy.position.x, y=enemy.position.y),
                patrol_index=enemy.patrol_index,
                reaction_available=enemy.reaction_available,
            )
            for enemy in state.enemies
        ],
    )


def _write_json_atomically(path: Path, data: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
        suffix=".tmp",
    ) as temp_file:
        json.dump(data, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)

    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
