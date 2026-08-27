"""Initialize selectors and initiative for a newly built encounter state."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..effects.conditions import CombatTrait
from .action_selection import build_action_selector
from .models import InitiativeEntry

if TYPE_CHECKING:
    from .encounter import EncounterState


def initialize_action_selectors(state: EncounterState) -> None:
    """Install the selectors used for external and automatic creature decisions."""

    state._action_selectors = {}
    for creature_ref, creature_state in state.creatures.items():
        state._action_selectors[creature_ref] = build_action_selector(
            state._creature_controller(creature_ref),
            creature_state,
        )


def roll_initiative(
    state: EncounterState,
    roll: Callable[[int], int],
) -> None:
    """Roll participants, order ties deterministically, and select the first turn."""

    entries: list[InitiativeEntry] = []
    for creature_ref, creature_state in state.creatures.items():
        participant = next(
            participant
            for participant in state.definition.participants
            if participant.creature_id == creature_ref
        )
        if not participant.takes_turns:
            continue
        die_result = roll(20)
        if state.effective_conditions_for(creature_ref).has_trait(
            CombatTrait.INITIATIVE_DISADVANTAGE
        ):
            die_result = min(die_result, roll(20))
        entries.append(
            InitiativeEntry(
                creature_ref=creature_ref,
                roll=die_result,
                modifier=creature_state.creature.get_modifier(
                    creature_state.creature.attributes.dexterity
                ),
                total=0,
            )
        )
    for entry in entries:
        entry.total = entry.roll + entry.modifier
    entries.sort(
        key=lambda entry: (
            -entry.total,
            -entry.modifier,
            entry.creature_ref,
        )
    )
    state.initiative_entries = entries
    state.initiative_order = [entry.creature_ref for entry in entries]
