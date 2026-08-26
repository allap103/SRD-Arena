"""Project serialized encounter state into a battlefield presentation."""

from __future__ import annotations

from typing import Any

from .conditions import effective_condition_names
from .models import BattlefieldCreatureView, BattlefieldView, GridPositionView

TEAM_COLORS = ("#3f7fd5", "#d64545", "#3fa45b", "#d5ad36", "#8a5bd1")


def build_battlefield_view(
    combat_state: dict[str, Any],
    *,
    background_image: str | None = None,
    grid_color: str = "#d3d3d3",
    grid_opacity: float = 1.0,
    team_ids: tuple[str, ...] = (),
) -> BattlefieldView:
    if len(team_ids) > len(TEAM_COLORS):
        raise ValueError("Battlefield presentation supports at most five teams.")
    team_colors = dict(zip(team_ids, TEAM_COLORS[: len(team_ids)], strict=True))
    decision = combat_state["decision"]
    concentrating_refs, buffs_by_ref, debuffs_by_ref = _battlefield_statuses(
        combat_state
    )
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
            conditions=effective_condition_names(creature),
            is_concentrating=creature_ref in concentrating_refs,
            buffs=buffs_by_ref.get(creature_ref, ()),
            debuffs=debuffs_by_ref.get(creature_ref, ()),
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


def _battlefield_statuses(
    combat_state: dict[str, Any],
) -> tuple[
    frozenset[str],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    """Collect concentration plus explicitly classified ongoing effects."""

    creatures = combat_state.get("creatures")
    if not isinstance(creatures, dict):
        return frozenset(), {}, {}

    concentrating_refs: set[str] = set()
    buffs: dict[str, list[str]] = {}
    debuffs: dict[str, list[str]] = {}
    ongoing_effects = combat_state.get("ongoing_effects")
    if not isinstance(ongoing_effects, list):
        return frozenset(), {}, {}

    for effect in ongoing_effects:
        if not isinstance(effect, dict):
            continue
        source = effect.get("source")
        if not isinstance(source, dict):
            continue
        source_ref = source.get("applied_by_ref")
        if effect.get("kind") == "concentration" and isinstance(source_ref, str):
            concentrating_refs.add(source_ref)

        polarity = effect.get("polarity")
        if polarity == "beneficial":
            collection = buffs
        elif polarity == "harmful":
            collection = debuffs
        else:
            continue

        label = _ongoing_effect_label(effect, source)
        target_refs = effect.get("target_refs")
        if label is None or not isinstance(target_refs, list):
            continue
        for target_ref in target_refs:
            if not isinstance(target_ref, str):
                continue
            labels = collection.setdefault(target_ref, [])
            if label not in labels:
                labels.append(label)

    return (
        frozenset(concentrating_refs),
        {creature_ref: tuple(labels) for creature_ref, labels in buffs.items()},
        {creature_ref: tuple(labels) for creature_ref, labels in debuffs.items()},
    )


def _ongoing_effect_label(
    effect: dict[str, Any],
    source: dict[str, Any],
) -> str | None:
    parameters = effect.get("parameters")
    if isinstance(parameters, dict):
        label = parameters.get("effect_label")
        if isinstance(label, str) and label.strip():
            return label
    definition_id = source.get("definition_id")
    if not isinstance(definition_id, str) or not definition_id.strip():
        return None
    return definition_id.replace("_", " ").replace("-", " ").title()


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
                    if creature["position"]["x"] == x and creature["position"]["y"] == y
                ),
                None,
            )
            row.append("E" if creature_here else ".")
        rows.append(" ".join(row))

    creature_lines = [
        (
            f"- Enemy {index + 1} ({enemy['name']}): {enemy['health']} HP at "
            f"({enemy['position']['x']}, {enemy['position']['y']})"
            f"{_condition_suffix(effective_condition_names(enemy))}"
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
                f"{_condition_suffix(effective_condition_names(actor_state))}"
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


def _condition_suffix(conditions: object) -> str:
    if not isinstance(conditions, (list, tuple)):
        return ""
    labels = [
        condition.capitalize() for condition in conditions if isinstance(condition, str)
    ]
    if not labels:
        return ""
    return f" [{', '.join(labels)}]"
