from types import SimpleNamespace

from srd_arena.domain.encounters.conditions import (
    apply_condition,
    apply_grapple,
    condition_replaces,
    remove_condition,
    remove_condition_from_source,
    remove_relationships_for_creature,
)
from srd_arena.domain.encounters.participants import (
    creatures_are_opponents,
    creature_controller,
    creature_team_id,
)
from srd_arena.domain.encounters import EncounterTeam
from srd_arena.domain.effects.conditions import Condition, build_applied_condition


def _condition(condition: Condition, source: str, target: str):
    return build_applied_condition(
        condition=condition,
        source_ref=source,
        source_label=source,
        target_ref=target,
    )


def test_apply_condition_refreshes_matching_condition_without_duplication() -> None:
    original = _condition(Condition.BLINDED, "goblin_1", "player")
    refreshed = build_applied_condition(
        condition=Condition.BLINDED,
        source_ref="goblin_1",
        source_label="goblin_1",
        target_ref="player",
        expires_on_creature_ref="player",
        expires_on_round=3,
    )
    state = SimpleNamespace(conditions=[original])

    apply_condition(state, refreshed)

    assert state.conditions == [refreshed]


def test_grappled_from_different_sources_do_not_replace_each_other() -> None:
    first = _condition(Condition.GRAPPLED, "goblin_1", "player")
    second = _condition(Condition.GRAPPLED, "goblin_2", "player")

    assert condition_replaces(first, second) is False


def test_removing_grappled_also_removes_matching_relationship() -> None:
    grappled = _condition(Condition.GRAPPLED, "goblin_1", "player")
    unrelated = _condition(Condition.BLINDED, "goblin_2", "player")
    state = SimpleNamespace(conditions=[unrelated], relationships=[])
    apply_grapple(state, grappled)

    remove_condition(state, "player", Condition.GRAPPLED)

    assert state.conditions == [unrelated]
    assert state.relationships == []


def test_removing_one_grapple_source_preserves_other_grapples() -> None:
    first = _condition(Condition.GRAPPLED, "goblin_1", "player")
    second = _condition(Condition.GRAPPLED, "goblin_2", "player")
    state = SimpleNamespace(conditions=[], relationships=[])
    apply_grapple(state, first)
    apply_grapple(state, second)

    remove_condition_from_source(
        state,
        "player",
        Condition.GRAPPLED,
        "goblin_1",
    )

    assert state.conditions == [second]
    assert [relationship.source_ref for relationship in state.relationships] == ["goblin_2"]


def test_defeated_creature_releases_all_grapple_relationships() -> None:
    grappled = _condition(Condition.GRAPPLED, "aboleth", "player")
    unrelated = _condition(Condition.BLINDED, "goblin_2", "player")
    state = SimpleNamespace(conditions=[unrelated], relationships=[])
    apply_grapple(state, grappled)

    remove_relationships_for_creature(state, "aboleth")

    assert state.conditions == [unrelated]
    assert state.relationships == []


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
