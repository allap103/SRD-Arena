from types import SimpleNamespace

from srd_arena.domain.encounters.conditions import (
    apply_status,
    remove_relational_statuses_for_creature,
    remove_status,
    remove_status_from_source,
    status_replaces,
)
from srd_arena.domain.encounters.participants import (
    creatures_are_opponents,
    creature_controller,
    creature_team_id,
)
from srd_arena.domain.encounters import EncounterTeam
from srd_arena.domain.effects.conditions import Status


def _status(name: str, source: str, target: str) -> Status:
    return Status(
        id=f"{name}:{source}:{target}",
        name=name,
        source_ref=source,
        source_label=source,
        target_ref=target,
    )


def test_apply_status_refreshes_matching_condition_without_duplication() -> None:
    original = _status("blinded", "goblin_1", "player")
    refreshed = Status(
        **{
            **original.__dict__,
            "expires_on_round": 3,
        }
    )
    state = SimpleNamespace(conditions=[original])

    apply_status(state, refreshed)

    assert state.conditions == [refreshed]


def test_relational_statuses_from_different_sources_do_not_replace_each_other() -> None:
    first = _status("grappled", "goblin_1", "player")
    second = _status("grappled", "goblin_2", "player")

    assert status_replaces(first, second) is False


def test_removing_grappled_also_removes_matching_grappling_status() -> None:
    grappled = _status("grappled", "goblin_1", "player")
    grappling = _status("grappling", "player", "goblin_1")
    unrelated = _status("blinded", "goblin_2", "player")
    state = SimpleNamespace(conditions=[grappled, grappling, unrelated])

    remove_status(state, "player", "grappled")

    assert state.conditions == [unrelated]


def test_removing_one_grapple_source_preserves_other_grapples() -> None:
    first_grappled = _status("grappled", "goblin_1", "player")
    first_grappling = _status("grappling", "player", "goblin_1")
    second_grappled = _status("grappled", "goblin_2", "player")
    second_grappling = _status("grappling", "player", "goblin_2")
    state = SimpleNamespace(
        conditions=[
            first_grappled,
            first_grappling,
            second_grappled,
            second_grappling,
        ]
    )

    remove_status_from_source(
        state,
        "player",
        "grappled",
        "goblin_1",
    )

    assert state.conditions == [second_grappled, second_grappling]


def test_defeated_creature_releases_all_relational_grapples() -> None:
    grappled = _status("grappled", "aboleth", "player")
    grappling = _status("grappling", "player", "aboleth")
    unrelated = _status("blinded", "goblin_2", "player")
    state = SimpleNamespace(conditions=[grappled, grappling, unrelated])

    remove_relational_statuses_for_creature(state, "aboleth")

    assert state.conditions == [unrelated]


def test_participant_queries_use_authored_teams_and_controllers() -> None:
    state = SimpleNamespace(
        creatures={
            "player": SimpleNamespace(creature_id="player"),
            "goblin_1": SimpleNamespace(creature_id="goblin"),
        },
        definition=SimpleNamespace(
            participants=[],
            teams=[
                EncounterTeam("heroes", "Heroes", ["player"], "external"),
                EncounterTeam("monsters", "Monsters", ["goblin"], "scripted"),
            ]
        ),
    )

    assert creature_team_id(state, "player") == "heroes"
    assert creature_team_id(state, "goblin_1") == "monsters"
    assert creature_controller(state, "goblin_1") == "scripted"
    assert creatures_are_opponents(state, "player", "goblin_1") is True
def test_authored_creature_controller_overrides_team_default() -> None:
    state = SimpleNamespace(
        creatures={"goblin_1": SimpleNamespace(creature_id="goblin")},
        definition=SimpleNamespace(
            participants=[
                SimpleNamespace(creature_id="goblin", controller="external"),
            ],
            teams=[
                EncounterTeam("monsters", "Monsters", ["goblin"], "scripted")
            ],
        ),
    )

    assert creature_controller(state, "goblin_1") == "external"
