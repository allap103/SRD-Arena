"""Public numbering reveals only records actually observed by the team."""

from dataclasses import replace

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.engine.api import Session
from srd_arena.engine.player_events import public_events_from_event
from srd_arena.engine.player_knowledge import TeamKnowledge


def _movement(seq: int, actor: str = "hero") -> CombatEvent:
    return CombatEvent(seq, "movement_resolved", creature_ref=actor)


def test_internal_sequence_changes_do_not_change_public_records() -> None:
    event = _movement(2)
    assert public_events_from_event(
        event, visible_creature_refs=frozenset({"hero"})
    ) == public_events_from_event(
        replace(event, seq=900), visible_creature_refs=frozenset({"hero"})
    )
    assert event.seq == 2


def test_hidden_events_leave_no_gaps_or_history_changes() -> None:
    baseline = TeamKnowledge("heroes")
    with_hidden = TeamKnowledge("heroes")
    baseline.record_events(
        (_movement(1), _movement(2)), fallback_visibility=frozenset({"hero"})
    )
    with_hidden.record_events(
        (_movement(100),), fallback_visibility=frozenset({"hero"})
    )
    with_hidden.record_events(tuple(_movement(n, "hidden") for n in range(101, 120)))
    with_hidden.record_events(
        (_movement(120),), fallback_visibility=frozenset({"hero"})
    )
    assert with_hidden.recent_events == baseline.recent_events
    assert [event.seq for event in with_hidden.recent_events] == [1, 2]


def test_multi_target_numbering_happens_after_visibility_filtering() -> None:
    event = CombatEvent(
        500,
        "spell_cast",
        creature_ref="mage",
        data={
            "spell_id": "fireball",
            "target_refs": ["a", "hidden", "b"],
        },
    )
    knowledge = TeamKnowledge("heroes")
    knowledge.record_events(
        (_movement(1), event, _movement(900)),
        fallback_visibility=frozenset({"hero", "a", "b"}),
    )
    assert [record.seq for record in knowledge.recent_events] == [1, 2, 3, 4]
    assert [record.target_ref for record in knowledge.recent_events[1:3]] == ["a", "b"]


def test_team_counters_are_independent_and_survive_history_eviction() -> None:
    heroes = TeamKnowledge("heroes")
    enemies = TeamKnowledge("enemies")
    events = tuple(
        replace(
            _movement(n),
            visible_by_team=(("heroes", frozenset({"hero"})), ("enemies", frozenset())),
        )
        for n in range(1, 11)
    )
    heroes.record_events(events)
    enemies.record_events(events)
    shared = replace(
        _movement(100),
        visible_by_team=(
            ("heroes", frozenset({"hero"})),
            ("enemies", frozenset({"hero"})),
        ),
    )
    heroes.record_events((shared,))
    enemies.record_events((shared,))
    assert [event.seq for event in heroes.recent_events] == list(range(4, 12))
    assert [event.seq for event in enemies.recent_events] == [1]


def test_session_reset_restarts_public_numbering() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe_player("heroes")
    session._record_player_events((_movement(40, "warlock"), _movement(90, "warlock")))
    assert [event.seq for event in session.observe_player("heroes").recent_events] == [
        1,
        2,
    ]
    session.reset()
    assert session.observe_player("heroes").recent_events == ()
    session._record_player_events((_movement(800, "warlock"),))
    assert [event.seq for event in session.observe_player("heroes").recent_events] == [
        1
    ]
