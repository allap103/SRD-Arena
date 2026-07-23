from __future__ import annotations

from dataclasses import dataclass

from ...domain.creatures.feature_actions import FeatureActionDefinition
from ...runtime.models import ActionView, SceneView
from ...runtime.session import Session

SYSTEM_ACTION_COUNT = 1
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
    conditions: tuple[str, ...]
    spell_slots: tuple["SpellSlotTrackView", ...]
    movement_remaining: int
    movement_total: int
    movement_remaining_feet: int
    movement_total_feet: int
    initiative: tuple["InitiativeTrackEntryView", ...] = ()

    def as_text(self) -> str:
        return "\n".join(
            [
                f"Health: {self.current_health}/{self.max_health}",
                f"Action: {self.action_status}",
                f"Bonus Action: {self.bonus_action_status}",
                f"Reaction: {self.reaction_status}",
                f"Conditions: {_condition_text(self.conditions)}",
                *[
                    f"{slot.level}: {'□' * slot.remaining}{'■' * (slot.maximum - slot.remaining)}"
                    for slot in self.spell_slots
                ],
                f"Movement: {self.movement_remaining_feet}/{self.movement_total_feet} ft",
            ]
        )


@dataclass
class GridPositionView:
    x: int
    y: int


@dataclass(frozen=True)
class SpellSlotTrackView:
    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class InitiativeTrackEntryView:
    actor_ref: str
    label: str
    total: int
    is_active: bool = False


@dataclass
class BattlefieldCreatureView:
    actor_ref: str
    actor_id: str
    label: str
    token_image: str | None
    position: GridPositionView
    health: int
    conditions: tuple[str, ...] = ()
    is_player: bool = False
    is_active: bool = False


@dataclass
class BattlefieldView:
    width: int
    height: int
    creatures: list[BattlefieldCreatureView]
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
    transition_message: str | None = None
    transition_action: ActionView | None = None


@dataclass
class SessionPresentation:
    scene_id: str
    story_text: str | None
    story_actions: list[ActionView]
    system_actions: list[ActionView]
    encounter: EncounterView | None = None


def build_session_presentation(
    session: Session,
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
        story_text="",
        story_actions=story_actions,
        system_actions=system_actions,
        encounter=EncounterView(
            narrative_text="",
            battlefield=_build_battlefield_view(combat_state),
            resources=resources,
            movement_actions=movement_actions,
            non_movement_actions=non_movement_actions,
            feature_actions=feature_actions,
            end_turn_action=end_turn_action,
            action_pane_title=action_pane_title,
            transition_message=(
                session.pending_scene_transition.message
                if session.pending_scene_transition is not None
                else None
            ),
            transition_action=(
                next(
                    (action for action in story_actions if action.kind == "system_continue_transition"),
                    None,
                )
                if session.pending_scene_transition is not None
                else None
            ),
        ),
    )


def _build_feature_actions(
    session: Session,
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
        current_health=player_state["health"],
        max_health=player_state["max_health"],
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
        conditions=tuple(
            condition
            for condition in player_state.get("conditions", [])
            if isinstance(condition, str)
        ),
        spell_slots=_build_spell_slot_tracks(player_state),
        movement_remaining=player_state["movement_remaining"],
        movement_total=player_state["movement_total"],
        movement_remaining_feet=player_state["movement_remaining_feet"],
        movement_total_feet=player_state["movement_total_feet"],
        initiative=_build_initiative_track(combat_state),
    )


def _build_battlefield_view(combat_state: dict[str, object]) -> BattlefieldView:
    decision = combat_state["decision"]
    creatures = [
        BattlefieldCreatureView(
            actor_ref="player",
            actor_id=combat_state["player"]["actor_id"],
            label=combat_state["player"]["name"],
            token_image=combat_state["player"].get("token_image"),
            position=GridPositionView(
                x=combat_state["player"]["position"]["x"],
                y=combat_state["player"]["position"]["y"],
            ),
            health=combat_state["player"]["health"],
            conditions=tuple(
                condition
                for condition in combat_state["player"].get("conditions", [])
                if isinstance(condition, str)
            ),
            is_player=True,
            is_active=decision["actor_ref"] == "player",
        )
    ]
    creatures.extend(
        BattlefieldCreatureView(
            actor_ref=enemy["actor_ref"],
            actor_id=enemy["actor_id"],
            label=f"Enemy {index + 1} ({enemy['name']})",
            token_image=enemy.get("token_image"),
            position=GridPositionView(
                x=enemy["position"]["x"],
                y=enemy["position"]["y"],
            ),
            health=enemy["health"],
            conditions=tuple(
                condition
                for condition in enemy.get("conditions", [])
                if isinstance(condition, str)
            ),
            is_active=decision["actor_ref"] == enemy["actor_ref"],
        )
        for index, enemy in enumerate(combat_state["enemies"])
        if enemy["is_alive"]
    )
    return BattlefieldView(
        width=combat_state["grid"]["width"],
        height=combat_state["grid"]["height"],
        creatures=creatures,
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
            f"{_condition_suffix(enemy.get('conditions', []))}"
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
                f"{_condition_suffix(player_state.get('conditions', []))}"
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


def _condition_text(conditions: tuple[str, ...]) -> str:
    if not conditions:
        return "None"
    return ", ".join(condition.capitalize() for condition in conditions)


def _condition_suffix(conditions: object) -> str:
    if not isinstance(conditions, (list, tuple)):
        return ""
    labels = [condition.capitalize() for condition in conditions if isinstance(condition, str)]
    if not labels:
        return ""
    return f" [{', '.join(labels)}]"


def _build_initiative_track(
    combat_state: dict[str, object],
) -> tuple[InitiativeTrackEntryView, ...]:
    initiative = combat_state.get("initiative", [])
    decision = combat_state.get("decision", {})
    active_creature_ref = (
        decision.get("actor_ref")
        if isinstance(decision, dict)
        else None
    )
    if not isinstance(initiative, list):
        return ()

    entries: list[InitiativeTrackEntryView] = []
    for entry in initiative:
        if not isinstance(entry, dict):
            continue
        actor_ref = entry.get("actor_ref")
        label = entry.get("label")
        total = entry.get("total")
        if not isinstance(actor_ref, str) or not isinstance(label, str) or not isinstance(total, int):
            continue
        entries.append(
            InitiativeTrackEntryView(
                actor_ref=actor_ref,
                label=label,
                total=total,
                is_active=actor_ref == active_creature_ref,
            )
        )
    return tuple(entries)


def _build_spell_slot_tracks(player_state: dict[str, object]) -> tuple[SpellSlotTrackView, ...]:
    slot_max = player_state.get("spell_slots_max", {})
    slot_remaining = player_state.get("spell_slots_remaining", {})
    if not isinstance(slot_max, dict) or not isinstance(slot_remaining, dict):
        return ()

    tracks: list[SpellSlotTrackView] = []
    for key, maximum in sorted(slot_max.items(), key=lambda item: int(item[0])):
        try:
            level = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(maximum, int) or maximum <= 0:
            continue
        remaining = slot_remaining.get(key, slot_remaining.get(level, maximum))
        if not isinstance(remaining, int):
            remaining = maximum
        tracks.append(
            SpellSlotTrackView(
                level=level,
                remaining=max(0, min(remaining, maximum)),
                maximum=maximum,
            )
        )
    return tuple(tracks)
