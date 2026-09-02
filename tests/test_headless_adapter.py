from pathlib import Path

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    ActionObservation,
    ActionReasonObservation,
    EncounterCompletionObservation,
    EncounterTerminationReason,
    GameObservation,
    SceneObservation,
)
from srd_arena.frontends.headless import (
    EpisodeState,
    EpisodeTruncationReason,
    HeadlessGameAdapter,
)

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


def test_headless_adapter_maps_numeric_actions_to_stable_ids() -> None:
    adapter = _adapter()
    observation = adapter.start_encounter("full_control_showcase")
    assert observation.encounter is not None

    action_map = adapter.decision_action_map()
    wait_slot = next(slot for slot in action_map.slots if slot.kind == "wait")
    result = adapter.select_action_index(
        wait_slot.index,
        expected_decision_id=action_map.decision_id,
    )

    assert tuple(slot.index for slot in action_map.slots) == tuple(
        range(len(action_map.slots))
    )
    assert tuple(slot.action_id for slot in action_map.slots) == tuple(
        sorted(slot.action_id for slot in action_map.slots)
    )
    assert all(not slot.kind.startswith("system_") for slot in action_map.slots)
    assert action_map.legal_action_mask[wait_slot.index] is True
    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == wait_slot.action_id


def test_numeric_action_selection_rejects_a_stale_decision() -> None:
    adapter = _adapter()
    observation = adapter.start_encounter("full_control_showcase")
    assert observation.encounter is not None
    action_map = adapter.decision_action_map()
    wait_slot = next(slot for slot in action_map.slots if slot.kind == "wait")

    stale = adapter.select_action_index(
        wait_slot.index,
        expected_decision_id="earlier-decision",
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_headless_adapter_owns_and_replaces_the_episode_seed() -> None:
    adapter = _adapter()

    initial = adapter.start_encounter("full_control_showcase", seed=41)
    assert initial.encounter is not None
    assert adapter.seed == 41

    reseeded = adapter.reset(seed=42)
    assert reseeded.encounter is not None
    reseeded_initiative = reseeded.encounter.initiative
    assert adapter.seed == 42

    replayed = adapter.reset()
    assert replayed.encounter is not None
    assert replayed.encounter.initiative == reseeded_initiative
    assert adapter.seed == 42


def test_headless_adapter_reports_and_clears_explicit_truncation() -> None:
    adapter = _adapter()
    observation = adapter.start_encounter("full_control_showcase")
    assert observation.encounter is not None
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )

    status = adapter.truncate(EpisodeTruncationReason.STEP_LIMIT)
    rejected = adapter.select_action(
        wait.id,
        expected_decision_id=observation.encounter.decision.id,
    )

    assert status.state is EpisodeState.TRUNCATED
    assert status.truncated is True
    assert status.terminated is False
    assert status.truncation_reason is EpisodeTruncationReason.STEP_LIMIT
    assert status.winning_team_id is None
    assert adapter.available_actions() == ()
    assert rejected.failure is not None
    assert rejected.failure.code == "episode_truncated"

    adapter.reset()

    assert adapter.episode_status().state is EpisodeState.ACTIVE


def test_headless_adapter_reports_rules_driven_termination() -> None:
    from unittest.mock import Mock

    completion = EncounterCompletionObservation(
        message="Encounter complete",
        reason=EncounterTerminationReason.LAST_TEAM_STANDING,
        winning_team_id="heroes",
    )
    observation = GameObservation(
        SceneObservation("fight", ()),
        None,
        completion,
        False,
    )
    session = Mock()
    session.observe.return_value = observation
    adapter = HeadlessGameAdapter(Mock())
    adapter._session = session

    status = adapter.episode_status()

    assert status.state is EpisodeState.TERMINATED
    assert status.terminated is True
    assert status.truncated is False
    assert status.termination_reason is EncounterTerminationReason.LAST_TEAM_STANDING
    assert status.winning_team_id == "heroes"
    with pytest.raises(RuntimeError, match="cannot be truncated"):
        adapter.truncate(EpisodeTruncationReason.TURN_LIMIT)


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
    encounter = Mock()
    encounter.decision.id = "turn:1"
    observation = GameObservation(
        SceneObservation("fight", (unsupported,)),
        encounter,
        None,
        False,
    )
    catalog, session = Mock(), Mock()
    catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
    catalog.load_encounter.return_value = Mock()
    session.observe.return_value = observation
    monkeypatch.setattr(
        "srd_arena.frontends.headless.adapter.Session",
        lambda _encounter, *, seed=None: session,
    )
    adapter = HeadlessGameAdapter(catalog)

    observed = adapter.start_encounter("demo")

    assert observed.scene.action_details[0].reasons == unsupported.reasons
    assert adapter.available_actions() == ()
    action_map = adapter.decision_action_map()
    assert tuple(slot.action_id for slot in action_map.slots) == ("animate-objects",)
    assert action_map.legal_action_mask == (False,)


def test_numeric_action_selection_rejects_an_illegal_or_unknown_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    unavailable = ActionObservation(
        "dash",
        "Dash",
        "action",
        "hero",
        availability="unavailable",
    )
    encounter = Mock()
    encounter.decision.id = "turn:1"
    observation = GameObservation(
        SceneObservation("fight", (unavailable,)),
        encounter,
        None,
        False,
    )
    catalog, session = Mock(), Mock()
    catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
    catalog.load_encounter.return_value = Mock()
    session.observe.return_value = observation
    monkeypatch.setattr(
        "srd_arena.frontends.headless.adapter.Session",
        lambda _encounter, *, seed=None: session,
    )
    adapter = HeadlessGameAdapter(catalog)
    adapter.start_encounter("demo")

    unavailable_result = adapter.select_action_index(
        0,
        expected_decision_id="turn:1",
    )
    unknown_result = adapter.select_action_index(
        1,
        expected_decision_id="turn:1",
    )

    assert unavailable_result.failure is not None
    assert unavailable_result.failure.code == "action_unavailable"
    assert unknown_result.failure is not None
    assert unknown_result.failure.code == "invalid_action_index"
