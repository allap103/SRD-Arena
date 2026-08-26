"""Build display-ready turn resources and initiative information."""

from __future__ import annotations

from typing import Any

from .conditions import effective_condition_names
from .models import (
    InitiativeTrackEntryView,
    ResourceSummaryView,
    SpellSlotTrackView,
)


def build_resource_summary(combat_state: dict[str, Any]) -> ResourceSummaryView:
    decision = combat_state["decision"]
    creature_ref = decision["creature_ref"]
    creature_state = combat_state["creatures"][creature_ref]
    normal_turn = decision["kind"] == "turn"
    return ResourceSummaryView(
        current_health=creature_state["health"],
        max_health=creature_state["max_health"],
        action_status=(
            "Ready"
            if normal_turn and creature_state["action_available"]
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
            if normal_turn and creature_state["bonus_action_available"]
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        reaction_status=("Ready" if creature_state["reaction_available"] else "Spent"),
        attacks_available=(
            creature_state["attacks_remaining"]
            if creature_state["attacks_remaining"] > 0
            else creature_state["attacks_per_attack_action"]
            if normal_turn and creature_state["action_available"]
            else 0
        ),
        conditions=effective_condition_names(creature_state),
        spell_slots=_build_spell_slot_tracks(creature_state),
        movement_remaining=creature_state["movement_remaining"],
        movement_total=creature_state["movement_total"],
        movement_remaining_feet=creature_state["movement_remaining_feet"],
        movement_total_feet=creature_state["movement_total_feet"],
        initiative=_build_initiative_track(combat_state),
    )


def _build_initiative_track(
    combat_state: dict[str, Any],
) -> tuple[InitiativeTrackEntryView, ...]:
    initiative = combat_state.get("initiative", [])
    decision = combat_state.get("decision", {})
    active_creature_ref = (
        decision.get("creature_ref") if isinstance(decision, dict) else None
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


def _build_spell_slot_tracks(
    creature_state: dict[str, object],
) -> tuple[SpellSlotTrackView, ...]:
    slot_max = creature_state.get("spell_slots_max", {})
    slot_remaining = creature_state.get("spell_slots_remaining", {})
    if not isinstance(slot_max, dict) or not isinstance(slot_remaining, dict):
        return ()

    tracks: list[SpellSlotTrackView] = []
    for key, maximum in sorted(slot_max.items(), key=lambda item: int(item[0])):
        try:
            level = int(key)
        except TypeError, ValueError:
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
