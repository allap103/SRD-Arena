from pathlib import Path

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    ActionObservation,
    ActionReasonObservation,
    DecisionObservation,
    EncounterCompletionObservation,
    EncounterTerminationReason,
    GameObservation,
    GridObservation,
    PlayerCommandResult,
    PlayerObservation,
    SceneObservation,
    SelectAction,
)
from srd_arena.frontends.headless import (
    EpisodeState,
    EpisodeTruncationReason,
    HeadlessGameAdapter,
)

ENCOUNTERS_ROOT = Path(__file__).parents[1] / "content" / "encounters"
FULL_CONTROL_ENCOUNTER_ID = "archive/full_control_showcase"


def _adapter() -> HeadlessGameAdapter:
    return HeadlessGameAdapter(EncounterCatalog(encounter_root=ENCOUNTERS_ROOT))


def _player_observation(
    *actions: ActionObservation,
    decision_id: str = "turn:1",
) -> PlayerObservation:
    return PlayerObservation(
        schema_id="player-observation-v1-draft",
        perspective_team_id="heroes",
        encounter_id="demo",
        grid=GridObservation(5, 5),
        round_number=1,
        decision=DecisionObservation(decision_id, "turn", "warlock"),
        creatures=(),
        initiative_order=("warlock",),
        action_details=actions,
        terrain=(),
        recent_events=(),
        completion=None,
        requires_automatic_advance=False,
    )


def test_player_action_map_and_submission_stay_on_player_safe_boundary() -> None:
    from unittest.mock import Mock

    action = ActionObservation("wait", "Wait", "wait", "warlock")
    observation = _player_observation(action)
    expected = PlayerCommandResult(update=Mock())
    session = Mock()
    session.observe_player.return_value = observation
    session.execute_player.return_value = expected
    adapter = HeadlessGameAdapter(Mock())
    adapter._session = session

    action_map = adapter.player_decision_action_map("heroes")
    result = adapter.select_player_action_index(
        "heroes",
        0,
        expected_decision_id=action_map.decision_id,
    )

    assert action_map.slots[0].action_id == "wait"
    assert action_map.legal_action_mask == (True,)
    assert result is expected
    session.execute.assert_not_called()
    session.execute_player.assert_called_once_with(
        "heroes",
        SelectAction("wait", "turn:1"),
    )


def test_start_player_encounter_returns_only_player_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    observation = _player_observation()
    catalog, session = Mock(), Mock()
    catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
    catalog.load_encounter.return_value = Mock()
    session.observe.return_value = Mock()
    session.observe_player.return_value = observation
    monkeypatch.setattr(
        "srd_arena.frontends.headless.adapter.Session",
        lambda _encounter, *, seed=None, decision_epoch=0: session,
    )

    result = HeadlessGameAdapter(catalog).start_player_encounter(
        "demo",
        "heroes",
        seed=42,
    )

    assert result is observation
    session.observe_player.assert_called_once_with("heroes")


def test_player_automatic_advance_uses_only_the_safe_session_method() -> None:
    from unittest.mock import Mock

    expected = Mock()
    session = Mock()
    session.advance_player_until_input_required.return_value = expected
    adapter = HeadlessGameAdapter(Mock())
    adapter._session = session

    result = adapter.advance_player_until_input_required("heroes")

    assert result is expected
    session.advance_until_input_required.assert_not_called()
    session.advance_player_until_input_required.assert_called_once_with("heroes")


def test_headless_adapter_drives_game_by_stable_ids() -> None:
    adapter = _adapter()
    encounters = adapter.available_encounters()

    assert any(encounter.id == FULL_CONTROL_ENCOUNTER_ID for encounter in encounters)

    observation = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
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
    observation = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
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
    observation = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
    assert observation.encounter is not None
    action_map = adapter.decision_action_map()
    wait_slot = next(slot for slot in action_map.slots if slot.kind == "wait")

    stale = adapter.select_action_index(
        wait_slot.index,
        expected_decision_id="earlier-decision",
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_numeric_action_selection_rejects_an_old_map_after_choices_change() -> None:
    adapter = _adapter()
    adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
    old_map = adapter.decision_action_map()
    drop_prone = next(slot for slot in old_map.slots if slot.kind == "drop_prone")

    accepted = adapter.select_action_index(
        drop_prone.index,
        expected_decision_id=old_map.decision_id,
    )
    assert accepted.accepted is True

    current_map = adapter.decision_action_map()
    assert current_map.decision_id != old_map.decision_id
    assert current_map.slots[drop_prone.index].action_id != drop_prone.action_id

    stale = adapter.select_action_index(
        drop_prone.index,
        expected_decision_id=old_map.decision_id,
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_starting_a_new_episode_invalidates_the_previous_decision_token() -> None:
    adapter = _adapter()
    first = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID, seed=42)
    assert first.encounter is not None
    old_decision_id = first.encounter.decision.id

    second = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID, seed=42)
    assert second.encounter is not None
    assert second.encounter.decision.id != old_decision_id
    wait = next(
        action for action in adapter.available_actions() if action.kind == "wait"
    )

    stale = adapter.select_action(
        wait.id,
        expected_decision_id=old_decision_id,
    )

    assert stale.failure is not None
    assert stale.failure.code == "stale_decision"


def test_headless_adapter_owns_and_replaces_the_episode_seed() -> None:
    adapter = _adapter()

    initial = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID, seed=41)
    assert initial.encounter is not None
    initial_decision_id = initial.encounter.decision.id
    assert adapter.seed == 41

    reseeded = adapter.reset(seed=42)
    assert reseeded.encounter is not None
    reseeded_initiative = reseeded.encounter.initiative
    assert reseeded.encounter.decision.id != initial_decision_id
    assert adapter.seed == 42

    replayed = adapter.reset()
    assert replayed.encounter is not None
    assert replayed.encounter.initiative == reseeded_initiative
    assert replayed.encounter.decision.id != reseeded.encounter.decision.id
    assert adapter.seed == 42


def test_seeded_reset_replays_a_multi_command_combat_trace() -> None:
    adapter = _adapter()
    adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID, seed=42)

    first_trace = _run_attack_and_wait_trace(adapter, steps=8)
    adapter.reset()
    replayed_trace = _run_attack_and_wait_trace(adapter, steps=8)

    assert replayed_trace == first_trace


def test_headless_adapter_reports_and_clears_explicit_truncation() -> None:
    adapter = _adapter()
    observation = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
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

    with pytest.raises(RuntimeError, match="must be reset"):
        adapter.truncate(EpisodeTruncationReason.TURN_LIMIT)

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
    observation = adapter.start_encounter(FULL_CONTROL_ENCOUNTER_ID)
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
        lambda _encounter, *, seed=None, decision_epoch=0: session,
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
        lambda _encounter, *, seed=None, decision_epoch=0: session,
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


def test_numeric_action_map_exposes_but_does_not_select_unconfigured_aims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    area = ActionObservation(
        "fireball",
        "Fireball",
        "spell",
        "mage",
        required_configuration="aim",
    )
    encounter = Mock()
    encounter.decision.id = "turn:1"
    observation = GameObservation(
        SceneObservation("fight", (area,)),
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
        lambda _encounter, *, seed=None, decision_epoch=0: session,
    )
    adapter = HeadlessGameAdapter(catalog)
    adapter.start_encounter("demo")

    action_map = adapter.decision_action_map()

    assert action_map.slots[0].required_configuration == "aim"
    assert action_map.legal_action_mask == (False,)


def _run_attack_and_wait_trace(
    adapter: HeadlessGameAdapter,
    *,
    steps: int,
) -> tuple[tuple[object, ...], ...]:
    trace: list[tuple[object, ...]] = []
    for _ in range(steps):
        observation = adapter.observe()
        assert observation.encounter is not None
        enabled = tuple(
            action
            for action in observation.scene.action_details
            if action.enabled and not action.kind.startswith("system_")
        )
        attacks = tuple(action for action in enabled if action.kind == "attack")
        action = (
            attacks[0]
            if attacks
            else next(option for option in enabled if option.kind == "wait")
        )
        result = adapter.select_action(
            action.id,
            expected_decision_id=observation.encounter.decision.id,
        )
        assert result.update is not None
        updated_encounter = result.update.observation.encounter
        assert updated_encounter is not None
        trace.append(
            (
                result.update.selected_action_id,
                result.update.messages,
                result.update.events,
                tuple(
                    (creature.creature_ref, creature.health)
                    for creature in updated_encounter.creatures
                ),
            )
        )
    return tuple(trace)
