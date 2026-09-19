"""Shared snapshots retain history and project players without live state access."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.domain.encounters.event_stream import create_event
from srd_arena.engine.api import Session
from srd_arena.engine.player_knowledge import TeamKnowledge
from srd_arena.engine.player_observations import project_player_observation


def _session() -> Session:
    return Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)


def test_detached_snapshot_is_the_source_for_both_views() -> None:
    session = _session()
    snapshot = session.observe_gameplay()
    expected = session.observe_player("heroes")
    assert snapshot.game == session.observe()
    assert snapshot.active_turn_ref is not None
    state = session.encounter_state
    assert state is not None
    state.creatures["warlock"].creature.take_damage(5)
    state.creatures["goblin_1"].creature.attributes.base_armor_class = 99
    with patch.object(session, "_read", side_effect=AssertionError("Live state read")):
        with patch.object(session, "observe_gameplay", return_value=snapshot):
            assert session.observe() == snapshot.game
        assert (
            project_player_observation(snapshot, "heroes", TeamKnowledge("heroes"))
            == expected
        )
    assert (
        session.observe_player("heroes").creature("warlock").health
        != expected.creature("warlock").health
    )


def test_history_is_complete_detached_and_independent_of_public_window() -> None:
    session = _session()
    session.observe_gameplay()
    nested = {"dice": [2, 3]}
    events = tuple(
        CombatEvent(
            n,
            "attack_resolved",
            creature_ref="warlock",
            data={"target_ref": "goblin_1", "damage": 1, "nested": nested},
        )
        for n in range(1, 12)
    )
    session._record_gameplay_events(events)
    snapshot = session.observe_gameplay()
    nested["dice"].append(9)
    assert len(snapshot.history) == 11
    payload = snapshot.history[0].data["nested"]
    assert isinstance(payload, Mapping)
    assert payload["dice"] == (2, 3)
    with pytest.raises(TypeError):
        payload["dice"] = ()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        snapshot.sunlight = True  # type: ignore[misc]
    knowledge = TeamKnowledge("heroes")
    player = project_player_observation(snapshot, "heroes", knowledge)
    assert len(player.recent_events) == 8
    assert player.creature("goblin_1").observed_damage_total == 11
    assert project_player_observation(snapshot, "heroes", knowledge) == player
    session._record_gameplay_events((CombatEvent(12, "movement_resolved", "warlock"),))
    assert len(snapshot.history) == 11
    assert len(session.observe_gameplay().history) == 12


def test_later_visibility_never_reveals_private_history() -> None:
    session = _session()
    session.observe_gameplay()
    state = session.encounter_state
    assert state is not None
    hidden = build_applied_condition(
        condition=Condition.INVISIBLE,
        source_ref="goblin_1",
        source_label="Invisible",
        target_ref="goblin_1",
    )
    state.conditions.append(hidden)
    secret = create_event(
        state,
        "attack_resolved",
        creature_ref="goblin_1",
        data={"target_ref": "goblin_1", "damage": 7},
    )
    session._record_gameplay_events((secret,))
    state.conditions.remove(hidden)
    snapshot = session.observe_gameplay()
    assert snapshot.history[-1].data["damage"] == 7
    player = project_player_observation(snapshot, "heroes", TeamKnowledge("heroes"))
    assert player.creature("goblin_1").currently_visible
    assert player.creature("goblin_1").observed_damage_total == 0
    assert not player.recent_events


def test_reset_clears_journal_and_external_projection_memory() -> None:
    session = _session()
    session.observe_gameplay()
    session._record_gameplay_events((CombatEvent(1, "movement_resolved", "warlock"),))
    before = session.observe_gameplay()
    knowledge = TeamKnowledge("heroes")
    assert project_player_observation(before, "heroes", knowledge).recent_events
    session.reset()
    after = session.observe_gameplay()
    assert after.episode_id != before.episode_id
    assert after.history == ()
    assert not project_player_observation(after, "heroes", knowledge).recent_events
    assert len(before.history) == 1


def test_player_projection_preserves_last_known_position() -> None:
    session = _session()
    knowledge = TeamKnowledge("heroes")
    before = project_player_observation(session.observe_gameplay(), "heroes", knowledge)
    state = session.encounter_state
    assert state is not None
    state.conditions.append(
        build_applied_condition(
            condition=Condition.INVISIBLE,
            source_ref="goblin_1",
            source_label="Invisible",
            target_ref="goblin_1",
        )
    )
    from srd_arena.domain.geometry import Position

    state.creatures["goblin_1"].position = Position(0, 0)
    snapshot = session.observe_gameplay()
    actual = next(
        row for row in snapshot.creatures if row.combat.creature_ref == "goblin_1"
    )
    assert actual.combat.position.x == 0
    after = project_player_observation(snapshot, "heroes", knowledge)
    assert after.creature("goblin_1").position == before.creature("goblin_1").position
    assert not after.creature("goblin_1").currently_visible


def test_new_headless_episode_resets_external_knowledge() -> None:
    from srd_arena.frontends.headless import HeadlessGameAdapter

    adapter = HeadlessGameAdapter(EncounterCatalog())
    adapter.start_encounter("warlock_training", seed=42)
    first = adapter.observe_gameplay()
    knowledge = TeamKnowledge("heroes")
    project_player_observation(first, "heroes", knowledge)
    knowledge.facts_for("goblin_1").observed_damage_total = 99
    adapter.start_encounter("warlock_training", seed=42)
    second = adapter.observe_gameplay()
    assert first.episode_id != second.episode_id
    player = project_player_observation(second, "heroes", knowledge)
    assert player.creature("goblin_1").observed_damage_total == 0
