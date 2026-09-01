from __future__ import annotations

from pathlib import Path

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.api import (
    AimAction,
    ConfirmTargeting,
    GameObservation,
    SelectAction,
    Session,
    SetResourceAllocation,
)
from srd_arena.engine.session import PendingEncounterCompletion

FULL_CONTROL_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "full_control_showcase"
)
MASS_HEAL_ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "mass_heal_allocation_showcase"
)
SPELL_DAMAGE_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "spell_damage_showcase"
)


def _session(encounter_id: str) -> Session:
    return Session(EncounterCatalog().load_encounter(encounter_id))


def _advance_to_actor(
    session: Session,
    creature_ref: str,
) -> GameObservation:
    for _ in range(20):
        observation = session.observe()
        assert observation.encounter is not None
        if observation.encounter.decision.creature_ref == creature_ref:
            return observation
        if observation.requires_automatic_advance:
            session.advance_until_input_required()
            continue
        wait = next(
            action
            for action in observation.scene.action_details
            if action.kind == "wait" and action.enabled
        )
        result = session.execute(
            SelectAction(wait.id, observation.encounter.decision.id)
        )
        assert result.update is not None
    raise AssertionError(f"Creature '{creature_ref}' did not receive a turn.")


def test_session_exposes_frontend_neutral_observations_and_commands() -> None:
    session = _session(FULL_CONTROL_ENCOUNTER_DIR.name)
    observation = session.observe()
    assert observation.encounter is not None
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = session.execute(SelectAction(wait.id, observation.encounter.decision.id))
    next_observation = session.observe()

    assert observation.requires_automatic_advance is False
    assert observation.encounter.decision.creature_ref
    assert observation.encounter.creatures
    assert result.update is not None
    assert result.update.selected_action_id == wait.id
    assert next_observation.scene.scene_id == observation.scene.scene_id


def test_restart_rewinds_seeded_encounter_randomness() -> None:
    session = Session(
        EncounterCatalog().load_encounter(FULL_CONTROL_ENCOUNTER_DIR.name),
        dice=DiceRoller.seeded(42),
    )
    session.observe()
    assert session.encounter_state is not None

    def random_signature() -> tuple[tuple[tuple[str, int], ...], tuple[int, ...]]:
        assert session.encounter_state is not None
        initiative = tuple(
            (entry.creature_ref, entry.roll)
            for entry in session.encounter_state.initiative_entries
        )
        following_rolls = tuple(
            session.encounter_state.dice.roll_die(sides) for sides in (20, 6, 8, 20)
        )
        return initiative, following_rolls

    first_run = random_signature()
    session.pending_encounter_completion = PendingEncounterCompletion(
        "Encounter complete"
    )

    result = session.choose("system-restart-encounter")

    assert result.selected_action_id == "system-restart-encounter"
    assert random_signature() == first_run


def test_session_rejects_stale_commands_before_execution() -> None:
    session = _session(FULL_CONTROL_ENCOUNTER_DIR.name)
    observation = session.observe()
    assert observation.encounter is not None
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = session.execute(SelectAction(wait.id, "old-decision"))

    assert result.accepted is False
    assert result.failure is not None
    assert result.failure.code == "stale_decision"
    assert session.observe().encounter == observation.encounter


def test_session_aims_an_advertised_area_action() -> None:
    session = _session(SPELL_DAMAGE_ENCOUNTER_DIR.name)
    observation = _advance_to_actor(session, "spectrum_adept")
    assert observation.encounter is not None
    fireball = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.source_id == "fireball" and action.enabled
    )
    assert fireball.source_label == "Fireball"
    assert fireball.source_level == 3
    assert fireball.target_ref is None
    assert fireball.area_preview is not None
    assert fireball.area_preview["shape"] == "radius"
    assert not hasattr(fireball, "value")

    result = session.execute(
        AimAction(
            action_id=fireball.id,
            x=6.5,
            y=3.5,
            expected_decision_id=observation.encounter.decision.id,
        )
    )

    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == fireball.id


def test_session_controls_numeric_target_allocation() -> None:
    session = _session(MASS_HEAL_ENCOUNTER_DIR.name)
    observation = session.observe()
    assert observation.encounter is not None
    cast = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.enabled
    )
    started = session.execute(SelectAction(cast.id, observation.encounter.decision.id))
    assert started.update is not None
    targeting = started.update.observation.encounter
    assert targeting is not None and targeting.targeting is not None
    assert targeting.targeting.resource_pool_total == 700

    allocation = session.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=200,
            expected_decision_id=targeting.decision.id,
        )
    )
    assert allocation.update is not None
    allocated = allocation.update.observation.encounter
    assert allocated is not None and allocated.targeting is not None
    assert allocated.targeting.resource_allocations[0].amount == 200

    invalid = session.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=201,
            expected_decision_id=allocated.decision.id,
        )
    )
    assert invalid.failure is not None
    assert invalid.failure.code == "invalid_allocation"

    confirmed = session.execute(
        ConfirmTargeting(expected_decision_id=allocated.decision.id)
    )
    assert confirmed.accepted is True
