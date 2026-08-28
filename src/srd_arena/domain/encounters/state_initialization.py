"""Initialize selectors and initiative for a newly built encounter state."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..effects.conditions import CombatTrait
from .action_selection import build_action_selector
from .encounter_models.state import InitiativeEntry

if TYPE_CHECKING:
    from .encounter import EncounterState


def initialize_action_selectors(state: EncounterState) -> None:
    """Install the selectors used for external and automatic creature decisions.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> state = SimpleNamespace(
    ...     creatures={"hero": object(), "goblin": object()},
    ...     _creature_controller=lambda ref: "external" if ref == "hero" else "scripted",
    ... )
    >>> with patch(
    ...     "srd_arena.domain.encounters.state_initialization.build_action_selector",
    ...     side_effect=lambda controller, participant: controller,
    ... ):
    ...     initialize_action_selectors(state)
    >>> state._action_selectors
    {'hero': 'external', 'goblin': 'scripted'}
    """

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
    """Roll participants, order ties deterministically, and select the first turn.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock
    >>> hero = SimpleNamespace(creature=Mock())
    >>> goblin = SimpleNamespace(creature=Mock())
    >>> hero.creature.attributes.dexterity = 14
    >>> goblin.creature.attributes.dexterity = 12
    >>> hero.creature.get_modifier.return_value = 2
    >>> goblin.creature.get_modifier.return_value = 1
    >>> participants = [
    ...     SimpleNamespace(creature_id="hero", takes_turns=True),
    ...     SimpleNamespace(creature_id="goblin", takes_turns=True),
    ... ]
    >>> no_traits = SimpleNamespace(has_trait=lambda trait: False)
    >>> state = SimpleNamespace(
    ...     creatures={"hero": hero, "goblin": goblin},
    ...     definition=SimpleNamespace(participants=participants),
    ...     effective_conditions_for=lambda ref: no_traits,
    ... )
    >>> rolls = iter((12, 15))
    >>> roll_initiative(state, lambda sides: next(rolls))
    >>> state.initiative_order
    ['goblin', 'hero']
    """

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
