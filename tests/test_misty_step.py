"""Verify Misty Step authoring and execution through the public engine API."""

from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import TeleportEffect, primary_effects
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters import CoverDegree, TerrainCell
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.geometry import Position
from srd_arena.engine.commands import AimAction, CommandResult
from srd_arena.engine.observation_models import ActionObservation
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import player_first_initiative

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session() -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session.observe()
    return session


def _misty_step_action(session: Session) -> ActionObservation:
    return next(
        action
        for action in session.observe().scene.action_details
        if action.source_id == "misty_step"
        and action.resource_level == 3
        and action.enabled
    )


def _cast_misty_step(
    session: Session,
    destination: Position,
) -> CommandResult:
    observation = session.observe()
    assert observation.encounter is not None
    action = _misty_step_action(session)
    return session.execute(
        AimAction(
            action.id,
            destination.x + 0.5,
            destination.y + 0.5,
            observation.encounter.decision.id,
        )
    )


def test_misty_step_translates_to_a_visible_thirty_foot_teleport() -> None:
    spell = build_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT).find("Misty Step", "XPHB")
    )

    assert spell.definition is not None
    assert primary_effects(spell.definition) == (TeleportEffect(30, True),)


def test_level_five_pact_caster_can_cast_misty_step_with_level_three_slot() -> None:
    session = _session()

    action = _misty_step_action(session)

    assert action.label == "Cast Misty Step (Level 3)"
    assert action.required_configuration == "aim"


def test_misty_step_relocates_without_spending_movement() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    warlock = state.creatures["warlock"]
    movement_before = warlock.movement_remaining

    result = _cast_misty_step(session, Position(5, 3))

    assert result.accepted
    assert warlock.position == Position(5, 3)
    assert warlock.movement_remaining == movement_before
    assert warlock.bonus_action_available is False
    assert warlock.bonus_action_used_this_turn is True
    assert warlock.creature.spellcasting is not None
    assert warlock.creature.spellcasting.spell_slots_remaining == {3: 1}


@pytest.mark.parametrize(
    ("destination", "message"),
    [
        (Position(2, 5), "unoccupied legal space"),
        (Position(11, 8), "out of range"),
    ],
)
def test_misty_step_rejects_illegal_destinations_without_spending_resources(
    destination: Position,
    message: str,
) -> None:
    session = _session()
    assert session.encounter_state is not None
    warlock = session.encounter_state.creatures["warlock"]

    result = _cast_misty_step(session, destination)

    assert result.update is not None
    rejection = result.update.events[-1]
    assert rejection.type == "action_resolved"
    assert rejection.data["success"] is False
    assert message in str(rejection.data["reason"])
    assert warlock.position == Position(2, 3)
    assert warlock.bonus_action_available is True
    assert warlock.bonus_action_used_this_turn is False
    assert warlock.creature.spellcasting is not None
    assert warlock.creature.spellcasting.spell_slots_remaining == {3: 2}


def test_misty_step_ends_a_grapple_separated_by_the_teleport() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["goblin_1"].position = Position(3, 3)
    applied = build_applied_condition(
        condition=Condition.GRAPPLED,
        source_ref="goblin_1",
        source_label="Goblin One",
        target_ref="warlock",
    )
    assert apply_grapple(state, applied).accepted

    result = _cast_misty_step(session, Position(5, 3))

    assert result.accepted
    assert not state.has_condition("warlock", Condition.GRAPPLED)
    assert state.relationships == []


def test_misty_step_rejects_a_destination_behind_total_cover() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.definition.terrain = (TerrainCell(Position(3, 3), cover=CoverDegree.TOTAL),)

    result = _cast_misty_step(session, Position(5, 3))

    assert result.update is not None
    rejection = result.update.events[-1]
    assert rejection.data["success"] is False
    assert rejection.data["reason_code"] == "teleport_destination_not_visible"
    assert state.creatures["warlock"].position == Position(2, 3)
