from types import SimpleNamespace

from srd_arena.domain.encounters.conditions import apply_status, remove_status, status_replaces
from srd_arena.domain.encounters.participants import (
    actors_are_opponents,
    creature_controller,
    creature_team_id,
)
from srd_arena.domain.scene import EncounterTeam
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
    state = SimpleNamespace(conditions=[original])

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
    state = SimpleNamespace(conditions=[grappled, grappling, unrelated])

    remove_status(state, "player", "grappled")

    assert state.conditions == [unrelated]


def test_participant_queries_use_authored_teams_and_controllers() -> None:
    state = SimpleNamespace(
        control_mode="default",
        enemies=[SimpleNamespace(actor_id="goblin")],
        definition=SimpleNamespace(
            teams=[
                EncounterTeam("heroes", "Heroes", ["player"], "user"),
                EncounterTeam("monsters", "Monsters", ["goblin"], "ai"),
            ]
        ),
    )

    assert creature_team_id(state, "player") == "heroes"
    assert creature_team_id(state, "enemy:0") == "monsters"
    assert creature_controller(state, "enemy:0") == "ai"
    assert actors_are_opponents(state, "player", "enemy:0") is True


def test_all_user_control_mode_overrides_authored_controller() -> None:
    state = SimpleNamespace(control_mode="all-user")

    assert creature_controller(state, "enemy:0") == "user"
