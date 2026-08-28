from types import SimpleNamespace
from typing import cast

from srd_arena.domain.creatures import CreatureStatistics
from srd_arena.domain.effects.conditions import (
    AppliedCondition,
    Condition,
    build_applied_condition,
)
from srd_arena.domain.effects.runtime import CreatureRelationship
from srd_arena.domain.encounters import EncounterTeam
from srd_arena.domain.encounters.conditions import (
    apply_condition,
    apply_grapple,
    condition_replaces,
    remove_condition,
    remove_condition_from_source,
    remove_relationships_for_creature,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.participants import (
    creature_controller,
    creature_team_id,
    creatures_are_opponents,
)


def _condition(
    condition: Condition,
    source: str,
    target: str,
) -> AppliedCondition:
    return build_applied_condition(
        condition=condition,
        source_ref=source,
        source_label=source,
        target_ref=target,
    )


def _condition_state(
    *,
    conditions: list[AppliedCondition] | None = None,
    relationships: list[CreatureRelationship] | None = None,
    immunities: frozenset[Condition] = frozenset(),
) -> EncounterState:
    return cast(
        EncounterState,
        SimpleNamespace(
            conditions=list(conditions or ()),
            relationships=list(relationships or ()),
            creatures={
                "player": SimpleNamespace(
                    creature=SimpleNamespace(
                        statistics=CreatureStatistics(condition_immunities=immunities),
                        condition_immunities=lambda: immunities,
                    )
                )
            },
        ),
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
    state = _condition_state(conditions=[original])

    apply_condition(state, refreshed)

    assert state.conditions == [refreshed]


def test_apply_condition_preserves_instances_from_distinct_origins() -> None:
    first = build_applied_condition(
        condition=Condition.BLINDED,
        source_ref="wizard",
        source_label="Wizard",
        target_ref="player",
        origin_id="spell:1",
    )
    second = build_applied_condition(
        condition=Condition.BLINDED,
        source_ref="wizard",
        source_label="Wizard",
        target_ref="player",
        origin_id="spell:2",
    )
    state = _condition_state()

    apply_condition(state, first)
    apply_condition(state, second)

    assert state.conditions == [first, second]


def test_condition_immunity_rejects_new_application() -> None:
    state = _condition_state(immunities=frozenset({Condition.PRONE}))

    result = apply_condition(state, _condition(Condition.PRONE, "wizard", "player"))

    assert result.accepted is False
    assert result.rejections[0].reason == "condition_immunity"
    assert state.conditions == []


def test_unconscious_applies_persistent_prone_consequence() -> None:
    state = _condition_state()

    result = apply_condition(
        state, _condition(Condition.UNCONSCIOUS, "wizard", "player")
    )
    remove_condition(state, "player", Condition.UNCONSCIOUS)

    assert result.accepted is True
    assert [condition.condition for condition in state.conditions] == [Condition.PRONE]


def test_prone_immunity_does_not_reject_unconscious() -> None:
    state = _condition_state(immunities=frozenset({Condition.PRONE}))

    result = apply_condition(
        state, _condition(Condition.UNCONSCIOUS, "wizard", "player")
    )

    assert result.accepted is True
    assert result.rejections[0].condition is Condition.PRONE
    assert [condition.condition for condition in state.conditions] == [
        Condition.UNCONSCIOUS
    ]


def test_grappled_from_different_sources_do_not_replace_each_other() -> None:
    first = _condition(Condition.GRAPPLED, "goblin_1", "player")
    second = _condition(Condition.GRAPPLED, "goblin_2", "player")

    assert condition_replaces(first, second) is False


def test_removing_grappled_also_removes_matching_relationship() -> None:
    grappled = _condition(Condition.GRAPPLED, "goblin_1", "player")
    unrelated = _condition(Condition.BLINDED, "goblin_2", "player")
    state = _condition_state(conditions=[unrelated])
    apply_grapple(state, grappled)

    remove_condition(state, "player", Condition.GRAPPLED)

    assert state.conditions == [unrelated]
    assert state.relationships == []


def test_removing_one_grapple_source_preserves_other_grapples() -> None:
    first = _condition(Condition.GRAPPLED, "goblin_1", "player")
    second = _condition(Condition.GRAPPLED, "goblin_2", "player")
    state = _condition_state()
    apply_grapple(state, first)
    apply_grapple(state, second)

    remove_condition_from_source(
        state,
        "player",
        Condition.GRAPPLED,
        "goblin_1",
    )

    assert state.conditions == [second]
    assert [relationship.source_ref for relationship in state.relationships] == [
        "goblin_2"
    ]


def test_defeated_creature_releases_all_grapple_relationships() -> None:
    grappled = _condition(Condition.GRAPPLED, "aboleth", "player")
    unrelated = _condition(Condition.BLINDED, "goblin_2", "player")
    state = _condition_state(conditions=[unrelated])
    apply_grapple(state, grappled)

    remove_relationships_for_creature(state, "aboleth")

    assert state.conditions == [unrelated]
    assert state.relationships == []


def test_participant_queries_use_authored_teams_and_controllers() -> None:
    state = cast(
        EncounterState,
        SimpleNamespace(
            creatures={
                "player": SimpleNamespace(creature_id="player"),
                "goblin_1": SimpleNamespace(creature_id="goblin"),
            },
            definition=SimpleNamespace(
                participants=[],
                teams=[
                    EncounterTeam("heroes", "Heroes", ["player"], "external"),
                    EncounterTeam("monsters", "Monsters", ["goblin"], "scripted"),
                ],
            ),
        ),
    )

    assert creature_team_id(state, "player") == "heroes"
    assert creature_team_id(state, "goblin_1") == "monsters"
    assert creature_controller(state, "goblin_1") == "scripted"
    assert creatures_are_opponents(state, "player", "goblin_1") is True


def test_authored_creature_controller_overrides_team_default() -> None:
    state = cast(
        EncounterState,
        SimpleNamespace(
            creatures={"goblin_1": SimpleNamespace(creature_id="goblin")},
            definition=SimpleNamespace(
                participants=[
                    SimpleNamespace(creature_id="goblin", controller="external"),
                ],
                teams=[EncounterTeam("monsters", "Monsters", ["goblin"], "scripted")],
            ),
        ),
    )

    assert creature_controller(state, "goblin_1") == "external"
