from types import SimpleNamespace
from typing import cast

from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.conditions import (
    apply_status,
    remove_status,
    status_replaces,
)
from srd_arena.domain.encounters.participants import (
    actors_are_opponents,
    creature_controller,
    creature_team_id,
)
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
    original = _status("blinded", "enemy:0", "player")
    refreshed = Status(
        **{
            **original.__dict__,
            "expires_on_round": 3,
        }
    )
    state = cast(EncounterState, SimpleNamespace(conditions=[original]))

    apply_status(state, refreshed)

    assert state.conditions == [refreshed]


def test_relational_statuses_from_different_sources_do_not_replace_each_other() -> None:
    first = _status("grappled", "enemy:0", "player")
    second = _status("grappled", "enemy:1", "player")

    assert status_replaces(first, second) is False


def test_removing_grappled_also_removes_matching_grappling_status() -> None:
    grappled = _status("grappled", "enemy:0", "player")
    grappling = _status("grappling", "player", "enemy:0")
    unrelated = _status("blinded", "enemy:1", "player")
    state = cast(
        EncounterState,
        SimpleNamespace(conditions=[grappled, grappling, unrelated]),
    )

    remove_status(state, "player", "grappled")

    assert state.conditions == [unrelated]


def test_participant_queries_use_authored_teams_and_controllers() -> None:
    combatants = {
        "player": SimpleNamespace(team_id="heroes", controller="external"),
        "enemy:0": SimpleNamespace(team_id="monsters", controller="scripted"),
    }
    state = cast(
        EncounterState,
        SimpleNamespace(
            combatant=lambda actor_ref: combatants[actor_ref],
        ),
    )

    assert creature_team_id(state, "player") == "heroes"
    assert creature_team_id(state, "enemy:0") == "monsters"
    assert creature_controller(state, "enemy:0") == "scripted"
    assert actors_are_opponents(state, "player", "enemy:0") is True
