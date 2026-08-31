"""Start, end, and advance creature turns in initiative order."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.runtime import UntilTurnEnd, UntilTurnStart
from srd_arena.domain.geometry import MovementBudget, MovementCost

from .attack_economy import clear_attack_action
from .effect_lifecycle.repeat_saves import resolve_end_turn_effects
from .effect_lifecycle.turn_start import expire_ongoing_effects_for_turn_start
from .encounter_models.actions import CreatureRef
from .encounter_models.resolution import EncounterProgress
from .grappling_state import is_grappled
from .participants import creature_team_id
from .rule_queries import movement_budget, reset_damage_reductions

if TYPE_CHECKING:
    from .encounter import EncounterState


def movement_budget_for_turn(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> MovementBudget:
    """Return the grid movement budget available at turn start.

    >>> from unittest.mock import Mock, patch
    >>> query = Mock(budget=MovementBudget(6))
    >>> with patch(
    ...     "srd_arena.domain.encounters.turn_lifecycle.movement_budget",
    ...     return_value=query,
    ... ):
    ...     int(movement_budget_for_turn(Mock(), "hero"))
    6
    """

    return movement_budget(state, creature_ref).budget


def active_turn_creature(state: EncounterState) -> CreatureRef:
    """Return the creature occupying the current initiative slot.

    >>> from unittest.mock import Mock
    >>> active_turn_creature(
    ...     Mock(initiative_order=["goblin", "hero"], turn=Mock(index=1)))
    'hero'
    """

    return state.initiative_order[state.turn.index]


def encounter_is_complete(state: EncounterState) -> bool:
    """Return whether only one configured team remains alive.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> state = SimpleNamespace(
    ...     creatures={
    ...         "hero": SimpleNamespace(is_alive=True),
    ...         "goblin": SimpleNamespace(is_alive=False),
    ...     },
    ... )
    >>> teams = {"hero": "heroes", "goblin": "foes"}
    >>> with patch(
    ...     "srd_arena.domain.encounters.turn_lifecycle.creature_team_id",
    ...     side_effect=lambda _state, ref: teams[ref],
    ... ):
    ...     encounter_is_complete(state)
    True
    """

    configured_teams = {
        creature_team_id(state, creature_ref) for creature_ref in state.creatures
    }
    living_teams = {
        creature_team_id(state, creature_ref)
        for creature_ref, creature_state in state.creatures.items()
        if creature_state.is_alive
    }
    return len(configured_teams) > 1 and len(living_teams) <= 1


def advance_turn(
    state: EncounterState,
    progress: EncounterProgress | None = None,
) -> None:
    """Run end hooks, advance initiative, and begin the next living turn.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock, patch
    >>> state = Mock(round=SimpleNamespace(number=2))
    >>> state.current_decision.return_value = SimpleNamespace(creature_ref="hero")
    >>> with (
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle.resolve_end_turn_effects"
    ...     ) as end_effects,
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle."
    ...         "expire_conditions_for_turn_end"
    ...     ),
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle._advance_initiative"
    ...     ),
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle._begin_turn_if_alive"
    ...     ),
    ... ):
    ...     advance_turn(state)
    >>> end_effects.assert_called_once_with(state, "hero", None)
    """

    ending_creature_ref = state.current_decision().creature_ref
    resolve_end_turn_effects(state, ending_creature_ref, progress)
    expire_conditions_for_turn_end(state, ending_creature_ref)
    _advance_initiative(state)
    _begin_turn_if_alive(state, progress)


def skip_defeated_turn(
    state: EncounterState,
    progress: EncounterProgress | None = None,
) -> None:
    """Advance one defeated initiative slot without running its turn hooks.

    >>> from unittest.mock import Mock, patch
    >>> state = Mock()
    >>> with (
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle._advance_initiative"
    ...     ) as advance,
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle._begin_turn_if_alive"
    ...     ),
    ... ):
    ...     skip_defeated_turn(state)
    >>> advance.assert_called_once_with(state)
    """

    _advance_initiative(state)
    _begin_turn_if_alive(state, progress)


def _advance_initiative(state: EncounterState) -> None:
    state.turn.index += 1
    if state.turn.index >= turn_count(state):
        state.turn.index = 0
        state.round.advance()


def _begin_turn_if_alive(
    state: EncounterState,
    progress: EncounterProgress | None,
) -> None:
    creature_ref = state.initiative_order[state.turn.index]
    creature_state = state.creatures[creature_ref]
    if not creature_state.is_alive:
        return
    reset_damage_reductions(state, creature_ref)
    expire_ongoing_effects_for_turn_start(state, creature_ref)
    expire_conditions_for_turn_start(state, creature_ref)
    from .actions.stat_block import recharge_stat_block_actions

    recharge_stat_block_actions(creature_state.creature, state.dice.roll_die)
    creature_state.movement_remaining = None
    creature_state.movement_spent_this_turn = MovementCost(0)
    creature_state.actions_remaining = 1
    creature_state.action_used_this_turn = False
    creature_state.magic_actions_remaining = 1
    clear_attack_action(creature_state)
    creature_state.bonus_action_available = True
    creature_state.bonus_action_used_this_turn = False
    if progress is not None:
        progress.messages.append(("turn", f"{creature_state.creature.name}'s turn"))


def expire_conditions_for_turn_end(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    """Remove conditions and child relationships ending with a creature's turn.

    >>> from types import SimpleNamespace
    >>> condition = SimpleNamespace(
    ...     id="blinded:1", duration=UntilTurnEnd("hero", 2)
    ... )
    >>> relationship = SimpleNamespace(
    ...     identity=SimpleNamespace(parent_id="blinded:1")
    ... )
    >>> state = SimpleNamespace(
    ...     conditions=[condition], relationships=[relationship],
    ...     round=SimpleNamespace(matches=lambda number: number == 2),
    ... )
    >>> expire_conditions_for_turn_end(state, "hero")
    >>> (state.conditions, state.relationships)
    ([], [])
    """

    expired_ids = {
        condition.id
        for condition in state.conditions
        if isinstance(condition.duration, UntilTurnEnd)
        and condition.duration.creature_ref == creature_ref
        and (
            condition.duration.round_number is None
            or state.round.matches(condition.duration.round_number)
        )
    }
    state.conditions = [
        condition for condition in state.conditions if condition.id not in expired_ids
    ]
    state.relationships = [
        relationship
        for relationship in state.relationships
        if relationship.identity.parent_id not in expired_ids
    ]


def expire_conditions_for_turn_start(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    """Remove conditions and child relationships ending at a creature's turn start.

    >>> from types import SimpleNamespace
    >>> condition = SimpleNamespace(
    ...     id="slowed:1", duration=UntilTurnStart("hero", 3)
    ... )
    >>> state = SimpleNamespace(
    ...     conditions=[condition], relationships=[],
    ...     round=SimpleNamespace(matches=lambda number: number == 3),
    ... )
    >>> expire_conditions_for_turn_start(state, "hero")
    >>> state.conditions
    []
    """

    expired_ids = {
        condition.id
        for condition in state.conditions
        if isinstance(condition.duration, UntilTurnStart)
        and condition.duration.creature_ref == creature_ref
        and (
            condition.duration.round_number is None
            or state.round.matches(condition.duration.round_number)
        )
    }
    state.conditions = [
        condition for condition in state.conditions if condition.id not in expired_ids
    ]
    state.relationships = [
        relationship
        for relationship in state.relationships
        if relationship.identity.parent_id not in expired_ids
    ]


def maybe_reset_reactions(state: EncounterState) -> None:
    """Restore reactions when initiative wraps to the first slot.

    >>> from types import SimpleNamespace
    >>> hero = SimpleNamespace(reaction_available=False)
    >>> state = SimpleNamespace(
    ...     turn=SimpleNamespace(index=0), creatures={"hero": hero}
    ... )
    >>> maybe_reset_reactions(state)
    >>> hero.reaction_available
    True
    """

    if state.turn.index != 0:
        return
    for creature_state in state.creatures.values():
        creature_state.reaction_available = True


def active_movement_remaining(state: EncounterState) -> MovementBudget:
    """Lazily initialize and return the active creature's movement budget.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> decision = SimpleNamespace(creature_ref="hero")
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: decision, active_movement_remaining=None
    ... )
    >>> query = SimpleNamespace(budget=MovementBudget(6))
    >>> with (
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle.is_grappled",
    ...         return_value=False,
    ...     ),
    ...     patch(
    ...         "srd_arena.domain.encounters.turn_lifecycle.movement_budget",
    ...         return_value=query,
    ...     ),
    ... ):
    ...     int(active_movement_remaining(state))
    6
    """

    creature_ref = state.current_decision().creature_ref
    if is_grappled(state, creature_ref):
        return MovementBudget(0)
    if state.active_movement_remaining is None:
        state.active_movement_remaining = movement_budget(state, creature_ref).budget
    return state.active_movement_remaining


def turn_count(state: EncounterState) -> int:
    """Return the number of initiative slots in the encounter.

    >>> from unittest.mock import Mock
    >>> turn_count(Mock(initiative_order=["hero", "goblin"]))
    2
    """

    return len(state.initiative_order)
