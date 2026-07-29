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
    original = _status("blinded", "participant:0", "player")
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
    first = _status("grappled", "participant:0", "player")
    second = _status("grappled", "participant:1", "player")

    assert status_replaces(first, second) is False


def test_removing_grappled_also_removes_matching_grappling_status() -> None:
    grappled = _status("grappled", "participant:0", "player")
    grappling = _status("grappling", "player", "participant:0")
    unrelated = _status("blinded", "participant:1", "player")
    state = SimpleNamespace(conditions=[grappled, grappling, unrelated])

    remove_status(state, "player", "grappled")

    assert state.conditions == [unrelated]


def test_removing_one_grapple_source_preserves_other_grapples() -> None:
    first_grappled = _status("grappled", "participant:0", "player")
    first_grappling = _status("grappling", "player", "participant:0")
    second_grappled = _status("grappled", "participant:1", "player")
    second_grappling = _status("grappling", "player", "participant:1")
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
        "participant:0",
    )

    assert state.conditions == [second_grappled, second_grappling]


def test_defeated_creature_releases_all_relational_grapples() -> None:
    grappled = _status("grappled", "aboleth", "player")
    grappling = _status("grappling", "player", "aboleth")
    unrelated = _status("blinded", "participant:1", "player")
    state = SimpleNamespace(conditions=[grappled, grappling, unrelated])

    remove_relational_statuses_for_creature(state, "aboleth")

    assert state.conditions == [unrelated]


def test_participant_queries_use_authored_teams_and_controllers() -> None:
    state = SimpleNamespace(
        creatures={
            "player": SimpleNamespace(creature_id="player"),
            "participant:0": SimpleNamespace(creature_id="goblin"),
        },
        definition=SimpleNamespace(
            participants=[],
            teams=[
                EncounterTeam("heroes", "Heroes", ["player"], "user"),
                EncounterTeam("monsters", "Monsters", ["goblin"], "ai"),
            ]
        ),
    )

    assert creature_team_id(state, "player") == "heroes"
    assert creature_team_id(state, "participant:0") == "monsters"
    assert creature_controller(state, "participant:0") == "ai"
    assert creatures_are_opponents(state, "player", "participant:0") is True
def test_authored_creature_controller_overrides_team_default() -> None:
    state = SimpleNamespace(
        creatures={"participant:0": SimpleNamespace(creature_id="goblin")},
        definition=SimpleNamespace(
            participants=[
                SimpleNamespace(creature_id="goblin", controller="user"),
            ],
            teams=[EncounterTeam("monsters", "Monsters", ["goblin"], "ai")],
        ),
    )

    assert creature_controller(state, "participant:0") == "user"
