from pathlib import Path

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    ActionObservation,
    ActionReasonObservation,
    GameObservation,
    SceneObservation,
)
from srd_arena.frontends.headless import HeadlessGameAdapter

ENCOUNTERS_ROOT = Path(__file__).parents[1] / "content" / "encounters"


def _adapter() -> HeadlessGameAdapter:
    return HeadlessGameAdapter(EncounterCatalog(encounter_root=ENCOUNTERS_ROOT))


def test_headless_adapter_drives_game_by_stable_ids() -> None:
    adapter = _adapter()
    encounters = adapter.available_encounters()

    assert any(encounter.id == "full_control_showcase" for encounter in encounters)

    observation = adapter.start_encounter("full_control_showcase")
    assert observation.encounter is not None
    decision_id = observation.encounter.decision.id
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )
    assert wait.id in adapter.available_action_ids()

    result = adapter.select_action(
        wait.id,
        expected_decision_id=decision_id,
    )

    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == wait.id
    assert result.update.observation.encounter is not None


def test_headless_adapter_preserves_stale_decision_protection() -> None:
    adapter = _adapter()
    observation = adapter.start_encounter("full_control_showcase")
    assert observation.encounter is not None
    old_decision_id = observation.encounter.decision.id
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )
    accepted = adapter.select_action(
        wait.id,
        expected_decision_id=old_decision_id,
    )
    assert accepted.update is not None

    stale = adapter.select_action(
        wait.id,
        expected_decision_id=old_decision_id,
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_headless_adapter_requires_a_started_game() -> None:
    adapter = _adapter()

    with pytest.raises(RuntimeError, match="Start an encounter"):
        adapter.observe()

    with pytest.raises(KeyError, match="Unknown encounter"):
        adapter.start_encounter("missing")


def test_headless_observation_preserves_unimplemented_action_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    unsupported = ActionObservation(
        "animate-objects",
        "Animate Objects",
        "spell",
        "mage",
        enabled=False,
        availability="unimplemented",
        reasons=(
            ActionReasonObservation(
                "unsupported_target_entities",
                "Areas that affect objects are not executable yet.",
            ),
        ),
    )
    observation = GameObservation(
        SceneObservation("fight", None, (unsupported,)),
        None,
        None,
        False,
    )
    catalog, session = Mock(), Mock()
    catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
    catalog.load_encounter.return_value = Mock()
    session.observe.return_value = observation
    monkeypatch.setattr(
        "srd_arena.frontends.headless.adapter.Session",
        lambda _encounter: session,
    )
    adapter = HeadlessGameAdapter(catalog)

    observed = adapter.start_encounter("demo")

    assert observed.scene.action_details[0].reasons == unsupported.reasons
    assert adapter.available_actions() == ()
