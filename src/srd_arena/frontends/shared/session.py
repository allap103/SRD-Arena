from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from ...domain.creatures.feature_actions import FeatureActionDefinition
from ...runtime.models import ActionView, SceneView
from ...runtime.session import Session
from .config import EncounterPresentationConfig

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
TEAM_COLORS = ("#3f7fd5", "#d64545", "#3fa45b", "#d5ad36", "#8a5bd1")


@dataclass
class ResourceSummaryView:
    current_health: int
    max_health: int
    action_status: str
    bonus_action_status: str
    reaction_status: str
    attacks_available: int
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
    creature_ref: str
    name: str
    total: int
    is_active: bool = False


@dataclass
class BattlefieldCreatureView:
    creature_ref: str
    creature_id: str
    name: str
    label: str
    token_image: str | None
    team_color: str
    position: GridPositionView
    health: int
    conditions: tuple[str, ...] = ()
    is_active: bool = False


@dataclass
class BattlefieldView:
    width: int
    height: int
    creatures: list[BattlefieldCreatureView]
    summary_text: str
    background_image: str | None = None
    grid_color: str = "#d3d3d3"
    grid_opacity: float = 1.0


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
    config: EncounterPresentationConfig | None = None,
) -> SessionPresentation:
    presentation_config = config or EncounterPresentationConfig()
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

    combat_state = cast(
        dict[str, Any],
        session.encounter_state.export_state(),
    )
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
            battlefield=_build_battlefield_view(
                combat_state,
                background_image=presentation_config.background_image,
                grid_color=presentation_config.grid_color,
                grid_opacity=presentation_config.grid_opacity,
                team_ids=tuple(
                    team.id for team in session.current_encounter.teams
                ),
            ),
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
    if session.encounter_state is None:
        return []
    creature_ref = session.encounter_state.current_decision().creature_ref
    creature = session.encounter_state.creatures[creature_ref].creature
    available_feature_actions = {
        str(action.value): action
        for action in story_actions
        if action.kind == "feature" and isinstance(action.value, str)
    }
    feature_actions: list[ActionView] = []
    for feature_id, definition in creature.combat_profile.feature_actions.items():
        available_action = available_feature_actions.get(feature_id)
        if available_action is not None:
            feature_actions.append(available_action)
            continue
        feature_actions.append(
            _build_unavailable_feature_action(definition, creature_ref)
        )
    return feature_actions


def _build_unavailable_feature_action(
    definition: FeatureActionDefinition,
    creature_ref: str,
) -> ActionView:
    cost = {definition.economy: 1} if definition.economy else {}
    return ActionView(
        index=-1,
        id=f"unavailable-feature-{definition.feature_id}",
        label=definition.label,
        kind="feature",
        creature_ref=creature_ref,
        value=definition.feature_id,
        cost=cost,
    )


def _build_resource_summary(combat_state: dict[str, Any]) -> ResourceSummaryView:
    decision = combat_state["decision"]
    creature_ref = decision["creature_ref"]
    creature_state = combat_state["creatures"][creature_ref]
    normal_turn = decision["kind"] == "turn"
    return ResourceSummaryView(
        current_health=creature_state["health"],
        max_health=creature_state["max_health"],
        action_status=(
            "Ready"
            if normal_turn
            and creature_state["action_available"]
            else f"{creature_state['attacks_remaining']} attack left"
            if normal_turn and creature_state["attacks_remaining"] == 1
            else f"{creature_state['attacks_remaining']} attacks left"
            if normal_turn and creature_state["attacks_remaining"] > 1
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        bonus_action_status=(
            "Ready"
            if normal_turn
            and creature_state["bonus_action_available"]
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        reaction_status="Ready" if creature_state["reaction_available"] else "Spent",
        attacks_available=(
            creature_state["attacks_remaining"]
            if creature_state["attacks_remaining"] > 0
            else creature_state["attacks_per_attack_action"]
            if normal_turn and creature_state["action_available"]
            else 0
        ),
        conditions=tuple(
            condition
            for condition in creature_state.get("conditions", [])
            if isinstance(condition, str)
        ),
        spell_slots=_build_spell_slot_tracks(creature_state),
        movement_remaining=creature_state["movement_remaining"],
        movement_total=creature_state["movement_total"],
        movement_remaining_feet=creature_state["movement_remaining_feet"],
        movement_total_feet=creature_state["movement_total_feet"],
        initiative=_build_initiative_track(combat_state),
    )


def _build_battlefield_view(
    combat_state: dict[str, Any],
    *,
    background_image: str | None = None,
    grid_color: str = "#d3d3d3",
    grid_opacity: float = 1.0,
    team_ids: tuple[str, ...] = (),
) -> BattlefieldView:
    if len(team_ids) > len(TEAM_COLORS):
        raise ValueError("Battlefield presentation supports at most five teams.")
    team_colors = dict(
        zip(team_ids, TEAM_COLORS[: len(team_ids)], strict=True)
    )
    decision = combat_state["decision"]
    creatures = [
        BattlefieldCreatureView(
            creature_ref=creature_ref,
            creature_id=creature["creature_id"],
            name=creature["name"],
            label=creature["label"],
            token_image=creature.get("token_image"),
            team_color=team_colors.get(creature.get("team_id"), TEAM_COLORS[0]),
            position=GridPositionView(
                x=creature["position"]["x"],
                y=creature["position"]["y"],
            ),
            health=creature["health"],
            conditions=tuple(
                condition
                for condition in creature.get("conditions", [])
                if isinstance(condition, str)
            ),
            is_active=decision["creature_ref"] == creature_ref,
        )
        for creature_ref, creature in combat_state["creatures"].items()
        if creature["is_alive"]
    ]
    return BattlefieldView(
        width=combat_state["grid"]["width"],
        height=combat_state["grid"]["height"],
        creatures=creatures,
        summary_text=_render_battlefield_text(combat_state),
        background_image=background_image,
        grid_color=grid_color,
        grid_opacity=grid_opacity,
    )


def _render_battlefield_text(combat_state: dict[str, Any]) -> str:
    width = combat_state["grid"]["width"]
    height = combat_state["grid"]["height"]
    creatures = combat_state["creatures"]
    actor_ref = combat_state["decision"]["creature_ref"]
    actor_state = creatures[actor_ref]
    actor_position = actor_state["position"]
    live_others = [
        creature
        for creature_ref, creature in creatures.items()
        if creature_ref != actor_ref and creature["is_alive"]
    ]

    rows: list[str] = []
    for y in range(height):
        row: list[str] = []
        for x in range(width):
            if actor_position["x"] == x and actor_position["y"] == y:
                row.append("A")
                continue
            creature_here = next(
                (
                    creature
                    for creature in live_others
                    if creature["position"]["x"] == x
                    and creature["position"]["y"] == y
                ),
                None,
            )
            row.append("E" if creature_here else ".")
        rows.append(" ".join(row))

    creature_lines = [
        (
            f"- Enemy {index + 1} ({enemy['name']}): {enemy['health']} HP at "
            f"({enemy['position']['x']}, {enemy['position']['y']})"
            f"{_condition_suffix(enemy.get('conditions', []))}"
        )
        for index, enemy in enumerate(live_others)
        if enemy["is_alive"]
    ]
    if not creature_lines:
        creature_lines = ["- No other creatures remaining."]

    turn_label = _turn_label(combat_state)
    return "\n".join(
        [
            *rows,
            "",
            f"Round {combat_state['round_number']} - Turn: {turn_label}",
            (
                f"{actor_state['name']} HP: "
                f"{actor_state['health']}/{actor_state['max_health']} "
                f"at ({actor_position['x']}, {actor_position['y']})"
                f"{_condition_suffix(actor_state.get('conditions', []))}"
            ),
            "Other creatures:",
            *creature_lines,
        ]
    )


def _turn_label(combat_state: dict[str, Any]) -> str:
    decision = combat_state["decision"]
    creature_ref = decision["creature_ref"]
    label = combat_state["creatures"][creature_ref]["label"]
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
    combat_state: dict[str, Any],
) -> tuple[InitiativeTrackEntryView, ...]:
    initiative = combat_state.get("initiative", [])
    decision = combat_state.get("decision", {})
    active_creature_ref = (
        decision.get("creature_ref")
        if isinstance(decision, dict)
        else None
    )
    if not isinstance(initiative, list):
        return ()

    entries: list[InitiativeTrackEntryView] = []
    creatures = combat_state.get("creatures", {})
    for entry in initiative:
        if not isinstance(entry, dict):
            continue
        creature_ref = entry.get("creature_ref")
        total = entry.get("total")
        creature_state = (
            creatures.get(creature_ref)
            if isinstance(creatures, dict) and isinstance(creature_ref, str)
            else None
        )
        name = creature_state.get("name") if isinstance(creature_state, dict) else None
        if (
            not isinstance(creature_ref, str)
            or not isinstance(name, str)
            or not isinstance(total, int)
        ):
            continue
        entries.append(
            InitiativeTrackEntryView(
                creature_ref=creature_ref,
                name=name,
                total=total,
                is_active=creature_ref == active_creature_ref,
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
