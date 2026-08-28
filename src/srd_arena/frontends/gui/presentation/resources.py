"""Build GUI-ready turn resources and initiative information."""

from __future__ import annotations

from srd_arena.application.api import CreatureObservation, EncounterObservation

from .conditions import effective_condition_names
from .models import (
    InitiativeTrackEntryView,
    ResourceSummaryView,
    SpellSlotTrackView,
)


def build_resource_summary(encounter: EncounterObservation) -> ResourceSummaryView:
    """Project the active combatant's health, economy, movement, and slots.

    >>> from types import SimpleNamespace
    >>> hero = SimpleNamespace(
    ...     health=9, max_health=12, action_available=True,
    ...     bonus_action_available=False, reaction_available=True,
    ...     attacks_remaining=0, attacks_per_attack_action=1,
    ...     effective_conditions=("prone",), spell_slots=(),
    ...     movement_remaining=4, movement_total=6,
    ...     movement_remaining_feet=20, movement_total_feet=30,
    ... )
    >>> encounter = SimpleNamespace(
    ...     decision=SimpleNamespace(creature_ref="hero", kind="turn"),
    ...     creature=lambda ref: hero, initiative=(),
    ... )
    >>> summary = build_resource_summary(encounter)
    >>> (summary.action_status, summary.bonus_action_status, summary.conditions)
    ('Ready', 'Spent', ('prone',))
    """

    decision = encounter.decision
    creature_state = encounter.creature(decision.creature_ref)
    normal_turn = decision.kind == "turn"
    return ResourceSummaryView(
        current_health=creature_state.health,
        max_health=creature_state.max_health,
        action_status=(
            "Ready"
            if normal_turn and creature_state.action_available
            else f"{creature_state.attacks_remaining} attack left"
            if normal_turn and creature_state.attacks_remaining == 1
            else f"{creature_state.attacks_remaining} attacks left"
            if normal_turn and creature_state.attacks_remaining > 1
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        bonus_action_status=(
            "Ready"
            if normal_turn and creature_state.bonus_action_available
            else "Spent"
            if normal_turn
            else "Waiting"
        ),
        reaction_status=("Ready" if creature_state.reaction_available else "Spent"),
        attacks_available=(
            creature_state.attacks_remaining
            if creature_state.attacks_remaining > 0
            else creature_state.attacks_per_attack_action
            if normal_turn and creature_state.action_available
            else 0
        ),
        conditions=effective_condition_names(creature_state),
        spell_slots=_build_spell_slot_tracks(creature_state),
        movement_remaining=creature_state.movement_remaining,
        movement_total=creature_state.movement_total,
        movement_remaining_feet=creature_state.movement_remaining_feet,
        movement_total_feet=creature_state.movement_total_feet,
        initiative=_build_initiative_track(encounter),
    )


def _build_initiative_track(
    encounter: EncounterObservation,
) -> tuple[InitiativeTrackEntryView, ...]:
    return tuple(
        InitiativeTrackEntryView(
            creature_ref=entry.creature_ref,
            name=encounter.creature(entry.creature_ref).name,
            total=entry.total,
            is_active=entry.creature_ref == encounter.decision.creature_ref,
        )
        for entry in encounter.initiative
    )


def _build_spell_slot_tracks(
    creature_state: CreatureObservation,
) -> tuple[SpellSlotTrackView, ...]:
    return tuple(
        SpellSlotTrackView(
            level=slot.level,
            remaining=max(0, min(slot.remaining, slot.maximum)),
            maximum=slot.maximum,
        )
        for slot in creature_state.spell_slots
    )
