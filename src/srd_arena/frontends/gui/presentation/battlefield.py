"""Project an observed encounter into the GUI battlefield presentation."""

from __future__ import annotations

from srd_arena.application.api import EncounterObservation

from .conditions import effective_condition_names
from .models import BattlefieldCreatureView, BattlefieldView, GridPositionView

TEAM_COLORS = ("#3f7fd5", "#d64545", "#3fa45b", "#d5ad36", "#8a5bd1")


def build_battlefield_view(
    encounter: EncounterObservation,
    *,
    background_image: str | None = None,
    grid_color: str = "#d3d3d3",
    grid_opacity: float = 1.0,
    team_ids: tuple[str, ...] = (),
) -> BattlefieldView:
    """Project an encounter observation into drawable grid and token data.

    >>> from types import SimpleNamespace
    >>> hero = SimpleNamespace(
    ...     creature_ref="hero", creature_id="hero", name="Hero", label="Hero",
    ...     token_image=None, team_id="heroes", position=SimpleNamespace(x=1, y=1),
    ...     health=10, max_health=10, is_alive=True, effective_conditions=(),
    ... )
    >>> encounter = SimpleNamespace(
    ...     grid=SimpleNamespace(width=3, height=3), round_number=1,
    ...     decision=SimpleNamespace(creature_ref="hero", kind="turn"),
    ...     creatures=(hero,), ongoing_effects=(), creature=lambda ref: hero,
    ... )
    >>> view = build_battlefield_view(encounter, team_ids=("heroes",))
    >>> (view.width, view.height, view.creatures[0].is_active)
    (3, 3, True)
    """

    if len(team_ids) > len(TEAM_COLORS):
        raise ValueError("Battlefield presentation supports at most five teams.")
    team_colors = dict(zip(team_ids, TEAM_COLORS[: len(team_ids)], strict=True))
    concentrating_refs, buffs_by_ref, debuffs_by_ref = _battlefield_statuses(encounter)
    creatures = [
        BattlefieldCreatureView(
            creature_ref=creature.creature_ref,
            creature_id=creature.creature_id,
            name=creature.name,
            label=creature.label,
            token_image=creature.token_image,
            team_color=team_colors.get(creature.team_id, TEAM_COLORS[0]),
            position=GridPositionView(
                x=creature.position.x,
                y=creature.position.y,
            ),
            health=creature.health,
            conditions=effective_condition_names(creature),
            is_concentrating=creature.creature_ref in concentrating_refs,
            buffs=buffs_by_ref.get(creature.creature_ref, ()),
            debuffs=debuffs_by_ref.get(creature.creature_ref, ()),
            is_active=encounter.decision.creature_ref == creature.creature_ref,
        )
        for creature in encounter.creatures
        if creature.is_alive
    ]
    return BattlefieldView(
        width=encounter.grid.width,
        height=encounter.grid.height,
        creatures=creatures,
        summary_text=_render_battlefield_text(encounter),
        background_image=background_image,
        grid_color=grid_color,
        grid_opacity=grid_opacity,
    )


def _battlefield_statuses(
    encounter: EncounterObservation,
) -> tuple[
    frozenset[str],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    """Collect concentration plus explicitly classified ongoing effects."""

    concentrating_refs: set[str] = set()
    buffs: dict[str, list[str]] = {}
    debuffs: dict[str, list[str]] = {}
    for effect in encounter.ongoing_effects:
        source_ref = effect.applied_by_ref
        if effect.kind == "concentration" and source_ref is not None:
            concentrating_refs.add(source_ref)

        if effect.polarity == "beneficial":
            collection = buffs
        elif effect.polarity == "harmful":
            collection = debuffs
        else:
            continue

        for target_ref in effect.target_refs:
            labels = collection.setdefault(target_ref, [])
            if effect.label not in labels:
                labels.append(effect.label)

    return (
        frozenset(concentrating_refs),
        {creature_ref: tuple(labels) for creature_ref, labels in buffs.items()},
        {creature_ref: tuple(labels) for creature_ref, labels in debuffs.items()},
    )


def _render_battlefield_text(encounter: EncounterObservation) -> str:
    width = encounter.grid.width
    height = encounter.grid.height
    actor_ref = encounter.decision.creature_ref
    actor_state = encounter.creature(actor_ref)
    actor_position = actor_state.position
    live_others = [
        creature
        for creature in encounter.creatures
        if creature.creature_ref != actor_ref and creature.is_alive
    ]

    rows: list[str] = []
    for y in range(height):
        row: list[str] = []
        for x in range(width):
            if actor_position.x == x and actor_position.y == y:
                row.append("A")
                continue
            creature_here = next(
                (
                    creature
                    for creature in live_others
                    if creature.position.x == x and creature.position.y == y
                ),
                None,
            )
            row.append("E" if creature_here else ".")
        rows.append(" ".join(row))

    creature_lines = [
        (
            f"- Enemy {index + 1} ({enemy.name}): {enemy.health} HP at "
            f"({enemy.position.x}, {enemy.position.y})"
            f"{_condition_suffix(effective_condition_names(enemy))}"
        )
        for index, enemy in enumerate(live_others)
        if enemy.is_alive
    ]
    if not creature_lines:
        creature_lines = ["- No other creatures remaining."]

    turn_label = _turn_label(encounter)
    return "\n".join(
        [
            *rows,
            "",
            f"Round {encounter.round_number} - Turn: {turn_label}",
            (
                f"{actor_state.name} HP: "
                f"{actor_state.health}/{actor_state.max_health} "
                f"at ({actor_position.x}, {actor_position.y})"
                f"{_condition_suffix(effective_condition_names(actor_state))}"
            ),
            "Other creatures:",
            *creature_lines,
        ]
    )


def _turn_label(encounter: EncounterObservation) -> str:
    decision = encounter.decision
    label = encounter.creature(decision.creature_ref).label
    if decision.kind == "reaction":
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
