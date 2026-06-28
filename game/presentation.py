from __future__ import annotations

from dataclasses import dataclass

from .models.class_features import FeatureActionDefinition
from .session import ActionView, GameSession, SceneView

SYSTEM_ACTION_COUNT = 3
MOVE_DIRECTIONS = (
    "up-left",
    "up",
    "up-right",
    "left",
    "right",
    "down-left",
    "down",
    "down-right",
)


@dataclass
class ResourceSummaryView:
    current_health: int
    max_health: int
    action_status: str
    bonus_action_status: str
    reaction_status: str
    movement_remaining: int
    movement_total: int
    movement_remaining_feet: int
    movement_total_feet: int

    def as_text(self) -> str:
        return "\n".join(
            [
                f"Health: {self.current_health}/{self.max_health}",
                f"Action: {self.action_status}",
                f"Bonus Action: {self.bonus_action_status}",
                f"Reaction: {self.reaction_status}",
                f"Movement: {self.movement_remaining_feet}/{self.movement_total_feet} ft",
            ]
        )


@dataclass
class GridPositionView:
    x: int
    y: int


@dataclass
class BattlefieldActorView:
    actor_ref: str
    actor_id: str
    label: str
    position: GridPositionView
    health: int
    is_player: bool = False
    is_active: bool = False


@dataclass
class BattlefieldView:
    width: int
    height: int
    actors: list[BattlefieldActorView]
    summary_text: str


@dataclass
class EncounterView:
    narrative_text: str | None
    battlefield: BattlefieldView
    resources: ResourceSummaryView
    movement_actions: dict[str, ActionView]
    non_movement_actions: list[ActionView]
    feature_actions: list[ActionView]
    end_turn_action: ActionView | None
    action_pane_title: str


@dataclass
class SessionPresentation:
    scene_id: str
    story_text: str | None
    story_actions: list[ActionView]
    system_actions: list[ActionView]
    encounter: EncounterView | None = None


def build_session_presentation(
    session: GameSession,
    scene_view: SceneView | None = None,
) -> SessionPresentation:
    view = scene_view or session.get_scene_view()
    story_actions = view.action_details[:-SYSTEM_ACTION_COUNT]
    system_actions = view.action_details[-SYSTEM_ACTION_COUNT:]

    if session.encounter_state is None:
        return SessionPresentation(
            scene_id=view.scene_id,
            story_text=view.scene_text,
            story_actions=story_actions,
            system_actions=system_actions,
        )

    combat_state = session.encounter_state.export_state(session.player)
    resources = _build_resource_summary(combat_state)
    movement_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "move" and isinstance(action.value, str)
    }
    non_movement_actions = [
        action
        for action in story_actions
        if action.kind not in {"move", "wait", "pass"}
    ]
    feature_actions = _build_feature_actions(session, story_actions)
    end_turn_action = next(
        (action for action in story_actions if action.kind in {"wait", "pass"}),
        None,
    )
    decision_kind = combat_state["decision"]["kind"]
    action_pane_title = (
        "Reactions"
        if decision_kind == "reaction"
        else "Reroll Damage"
        if decision_kind == "reroll_dice"
        else "Actions"
    )
    return SessionPresentation(
        scene_id=view.scene_id,
        story_text=session.current_scene.text,
        story_actions=story_actions,
        system_actions=system_actions,
        encounter=EncounterView(
            narrative_text=session.current_scene.text,
            battlefield=_build_battlefield_view(combat_state),
            resources=resources,
            movement_actions=movement_actions,
            non_movement_actions=non_movement_actions,
            feature_actions=feature_actions,
            end_turn_action=end_turn_action,
            action_pane_title=action_pane_title,
        ),
    )


def _build_feature_actions(
    session: GameSession,
    story_actions: list[ActionView],
) -> list[ActionView]:
    if (
        session.encounter_state is not None
        and session.encounter_state.current_decision().actor_ref != "player"
    ):
        return []
    available_feature_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "feature" and isinstance(action.value, str)
    }
    feature_actions: list[ActionView] = []
    for feature_id, definition in session.player.combat_profile.feature_actions.items():
        available_action = available_feature_actions.get(feature_id)
        if available_action is not None:
            feature_actions.append(available_action)
            continue
        feature_actions.append(_build_unavailable_feature_action(definition))
    return feature_actions


def _build_unavailable_feature_action(definition: FeatureActionDefinition) -> ActionView:
    cost = {definition.economy: 1} if definition.economy else {}
    return ActionView(
        index=-1,
        id=f"unavailable-feature-{definition.feature_id}",
        label=definition.label,
        kind="feature",
        actor_ref="player",
        value=definition.feature_id,
        cost=cost,
    )


def _build_resource_summary(combat_state: dict[str, object]) -> ResourceSummaryView:
    player_state = combat_state["player"]
    decision = combat_state["decision"]
    actor_ref = decision["actor_ref"]
    actor_state = (
        player_state
        if actor_ref == "player"
        else next(
            enemy
            for enemy in combat_state["enemies"]
            if enemy["actor_ref"] == actor_ref
        )
    )
    normal_turn = decision["kind"] == "turn"
    return ResourceSummaryView(
        current_health=actor_state["health"],
        max_health=actor_state["max_health"],
        action_status=(
            "Ready"
            if normal_turn
            and (
                actor_ref != "player"
                or player_state["action_available"]
            )
            else f"{player_state['attacks_remaining']} attack left"
            if normal_turn and player_state["attacks_remaining"] == 1
            else f"{player_state['attacks_remaining']} attacks left"
            if normal_turn and player_state["attacks_remaining"] > 1
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        bonus_action_status=(
            "Ready"
            if normal_turn
            and actor_ref == "player"
            and player_state["bonus_action_available"]
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        reaction_status="Ready" if actor_state["reaction_available"] else "Spent",
        movement_remaining=actor_state["movement_remaining"],
        movement_total=actor_state["movement_total"],
        movement_remaining_feet=actor_state["movement_remaining_feet"],
        movement_total_feet=actor_state["movement_total_feet"],
    )


def _build_battlefield_view(combat_state: dict[str, object]) -> BattlefieldView:
    decision = combat_state["decision"]
    actors = [
        BattlefieldActorView(
            actor_ref="player",
            actor_id=combat_state["player"]["actor_id"],
            label=combat_state["player"]["name"],
            position=GridPositionView(
                x=combat_state["player"]["position"]["x"],
                y=combat_state["player"]["position"]["y"],
            ),
            health=combat_state["player"]["health"],
            is_player=True,
            is_active=decision["actor_ref"] == "player",
        )
    ]
    actors.extend(
        BattlefieldActorView(
            actor_ref=enemy["actor_ref"],
            actor_id=enemy["actor_id"],
            label=f"Enemy {index + 1} ({enemy['name']})",
            position=GridPositionView(
                x=enemy["position"]["x"],
                y=enemy["position"]["y"],
            ),
            health=enemy["health"],
            is_active=decision["actor_ref"] == enemy["actor_ref"],
        )
        for index, enemy in enumerate(combat_state["enemies"])
        if enemy["is_alive"]
    )
    return BattlefieldView(
        width=combat_state["grid"]["width"],
        height=combat_state["grid"]["height"],
        actors=actors,
        summary_text=_render_battlefield_text(combat_state),
    )


def _render_battlefield_text(combat_state: dict[str, object]) -> str:
    width = combat_state["grid"]["width"]
    height = combat_state["grid"]["height"]
    player_state = combat_state["player"]
    player_position = player_state["position"]
    live_enemies = [enemy for enemy in combat_state["enemies"] if enemy["is_alive"]]

    rows: list[str] = []
    for y in range(height):
        row: list[str] = []
        for x in range(width):
            if player_position["x"] == x and player_position["y"] == y:
                row.append("P")
                continue
            enemy_here = next(
                (
                    enemy
                    for enemy in live_enemies
                    if enemy["position"]["x"] == x and enemy["position"]["y"] == y
                ),
                None,
            )
            row.append("E" if enemy_here else ".")
        rows.append(" ".join(row))

    enemy_lines = [
        (
            f"- Enemy {index + 1} ({enemy['name']}): {enemy['health']} HP at "
            f"({enemy['position']['x']}, {enemy['position']['y']})"
        )
        for index, enemy in enumerate(combat_state["enemies"])
        if enemy["is_alive"]
    ]
    if not enemy_lines:
        enemy_lines = ["- No enemies remaining."]

    turn_label = _turn_label(combat_state)
    return "\n".join(
        [
            *rows,
            "",
            f"Round {combat_state['round_number']} - Turn: {turn_label}",
            (
                f"Player HP: {player_state['health']}/{player_state['max_health']} "
                f"at ({player_position['x']}, {player_position['y']})"
            ),
            "Enemies:",
            *enemy_lines,
        ]
    )


def _turn_label(combat_state: dict[str, object]) -> str:
    decision = combat_state["decision"]
    actor_ref = decision["actor_ref"]
    if actor_ref == "player":
        return "Player" if decision["kind"] != "reaction" else "Player (Reaction)"
    enemy_index = int(actor_ref.split(":")[1])
    enemy = combat_state["enemies"][enemy_index]
    label = f"Enemy {enemy_index + 1} ({enemy['name']})"
    if decision["kind"] == "reaction":
        return f"{label} (Reaction)"
    return label
