"""Verify Alert's Initiative proficiency and optional ally swap."""

from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.queries import InitiativeSwapOptionDetails
from srd_arena.engine.session import Session

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _alert_session() -> Session:
    """Build the canonical party with deterministic real Initiative rolls."""

    rolls = iter((5, 15, 12, 11, 10))
    session = Session(
        load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR),
        dice=DiceRoller(die_roller=lambda _sides: next(rolls)),
    )
    session._read()
    return session


def test_alert_adds_proficiency_to_each_selected_characters_initiative() -> None:
    """Add each level-five Alert owner's +3 proficiency bonus to Initiative."""

    session = _alert_session()
    state = session.encounter_state
    assert state is not None
    entries = {entry.creature_ref: entry for entry in state.initiative_entries}

    assert entries["warlock"].modifier == 6
    assert entries["warlock"].total == 11
    assert entries["barbarian"].modifier == 6
    assert entries["barbarian"].total == 21
    assert entries["goblin_1"].modifier == 2


def test_external_alert_owner_can_swap_initiative_with_scripted_ally() -> None:
    """Expose, resolve, and observe the canonical Warlock-Barbarian swap."""

    session = _alert_session()
    state = session.encounter_state
    assert state is not None
    decision = state.current_decision()
    assert decision.kind == "initiative_swap"
    assert decision.creature_ref == "warlock"

    read = session._read()
    swap = next(
        option for option in read.action_options if option.kind == "swap_initiative"
    )
    keep = next(
        option for option in read.action_options if option.kind == "keep_initiative"
    )
    assert swap.label == "Swap initiative with Barbarian (barbarian)"
    assert isinstance(swap.details, InitiativeSwapOptionDetails)
    assert swap.details.target_ref == "barbarian"
    assert isinstance(keep.details, InitiativeSwapOptionDetails)
    assert keep.details.target_ref is None
    observed_swap = next(
        option
        for option in session.observe().scene.action_details
        if option.id == swap.id
    )
    assert observed_swap.target_ref == "barbarian"

    outcome = session._choose(swap.id)

    totals = {entry.creature_ref: entry.total for entry in state.initiative_entries}
    assert totals["warlock"] == 21
    assert totals["barbarian"] == 11
    assert state.initiative_order[0] == "warlock"
    assert state.current_decision().kind == "turn"
    event = next(
        event for event in outcome.events if event.type == "initiative_swap_resolved"
    )
    assert event.data["feature_id"] == "alert"
    assert event.data["target_ref"] == "barbarian"
    assert event.data["swapped"] is True


def test_alert_can_keep_initiative_and_incapacitation_removes_ally() -> None:
    """Keep the roll by choice and reject a newly incapacitated swap partner."""

    session = _alert_session()
    state = session.encounter_state
    assert state is not None
    state.conditions.append(
        build_applied_condition(
            condition=Condition.INCAPACITATED,
            source_ref="goblin_1",
            source_label="Goblin One",
            target_ref="barbarian",
        )
    )

    read = session._read()
    assert [
        option.kind for option in read.action_options if option.kind != "system_exit"
    ] == ["keep_initiative"]
    initial_order = list(state.initiative_order)
    keep = next(
        option for option in read.action_options if option.kind == "keep_initiative"
    )

    outcome = session._choose(keep.id)

    assert state.initiative_order == initial_order
    event = next(
        event for event in outcome.events if event.type == "initiative_swap_resolved"
    )
    assert event.data["target_ref"] is None
    assert event.data["swapped"] is False
