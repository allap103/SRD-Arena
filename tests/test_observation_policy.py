"""Executable grammar, disclosure, evidence, and replay contracts."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    GameplayEventObservation,
    ObservationPolicy,
    PolicyProjector,
    Session,
)
from srd_arena.engine.filtered_observations import HealthInterval, health_interval
from srd_arena.engine.observation_policy import HealthIntervals
from srd_arena.frontends.headless.config import (
    PolicyConfigError,
    load_policy,
    policy_digest,
)
from srd_arena.frontends.headless.serialization import canonical_json

PRESET = Path("config/observations/player.yaml")


def policy_with(**changes: object) -> ObservationPolicy:
    """Apply dotted overrides through strict revalidation."""
    data = load_policy(PRESET).model_dump(mode="json")
    for path, value in changes.items():
        parts = path.split(".")
        node = data
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    policy = ObservationPolicy.model_validate_json(canonical_json(data))
    policy.validate_support()
    return policy


@pytest.mark.parametrize("name", ["player", "visible-health", "hidden-health"])
def test_supported_presets_are_frozen(name: str) -> None:
    policy = load_policy(Path(f"config/observations/{name}.yaml"))
    with pytest.raises(ValidationError):
        policy.creatures.health.disclosure.enemy = "exact"


@pytest.mark.parametrize(
    "source,match",
    [
        ("schema_version: 1\nschema_version: 1", "Duplicate key"),
        ("a: &anchor 1\nb: *anchor", "anchors"),
        ("a: !!str hello", "tags"),
        ("a: !custom hello", "tags"),
        ("a: {<<: {x: 1}}", "merge"),
        ("a: " + "[" * 17 + "0" + "]" * 17, "nesting"),
        ("#" * 65537, "exceeds"),
        ("name: .nan", "JSON compliant"),
        ("schema_version: 1\n---\nname: another", "single document"),
    ],
)
def test_unsafe_yaml_rejected(tmp_path: Path, source: str, match: str) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(source)
    with pytest.raises(PolicyConfigError, match=match):
        load_policy(path)


@pytest.mark.parametrize(
    "path,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", "1"),
        ("history.recent_event_limit", True),
        ("history.recent_event_limit", -1),
        ("history.recent_event_limit", 10001),
        ("creatures.health.disclosure.enemy", "band"),
        ("creatures.health.intervals.boundaries", [0, 0.5, 0.5, 1]),
        ("creatures.health.intervals.boundaries", [0, 1, 0.5]),
        ("creatures.health.intervals.boundaries", [0, True, 1]),
        ("creatures.health.intervals.distinguish_full_health", "true"),
    ],
)
def test_strict_types_and_interval_grammar(path: str, value: object) -> None:
    with pytest.raises(ValueError):
        policy_with(**{path: value})


def test_extra_missing_and_unsupported_keys(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(PRESET.read_text() + "\nunknown: true\n")
    with pytest.raises(PolicyConfigError, match="unknown"):
        load_policy(path)
    path.write_text(
        PRESET.read_text().replace(
            "  knowledge_sharing: team", "  knowledge_sharing: individual"
        )
    )
    with pytest.raises(PolicyConfigError, match=r"perspective\.knowledge_sharing"):
        load_policy(path)
    with pytest.raises(ValueError, match=r"creatures\.health\.disclosure\.own"):
        policy_with(**{"creatures.health.disclosure.own": "hidden"})
    with pytest.raises(ValueError, match="require hidden"):
        policy_with(**{"creatures.effects.duration.enemy": "exact"})
    with pytest.raises(ValueError, match="require accumulation"):
        policy_with(**{"creatures.defenses.enemy": "demonstrated"})


def test_digest_ignores_yaml_order_and_comments(tmp_path: Path) -> None:
    policy = load_policy(PRESET)
    # JSON is a subset of YAML; this also exercises alternate mapping order.
    path = tmp_path / "policy.yaml"
    path.write_text(canonical_json(policy) + "\n# comment\n")
    assert policy_digest(load_policy(path)) == policy_digest(policy)
    assert policy_digest(policy_with(**{"history.events": "hidden"})) != policy_digest(
        policy
    )


@pytest.mark.parametrize(
    "hp,expected",
    [
        (0, HealthInterval(0, 0, True, True)),
        (1, HealthInterval(0, 0.25, False, True)),
        (25, HealthInterval(0, 0.25, False, True)),
        (26, HealthInterval(0.25, 0.5, False, True)),
        (50, HealthInterval(0.25, 0.5, False, True)),
        (75, HealthInterval(0.5, 0.75, False, True)),
        (99, HealthInterval(0.75, 1, False, False)),
        (100, HealthInterval(1, 1, True, True)),
        (120, HealthInterval(1, 1, True, True)),
    ],
)
def test_interval_endpoints(hp: int, expected: HealthInterval) -> None:
    settings = HealthIntervals(
        boundaries=(0.0, 0.25, 0.5, 0.75, 1.0), distinguish_full_health=True
    )
    assert health_interval(hp, 100, settings) == expected
    with pytest.raises(ValueError, match="positive"):
        health_interval(hp, 0, settings)
    assert health_interval(
        100, 100, settings.model_copy(update={"distinguish_full_health": False})
    ) == HealthInterval(0.75, 1, False, True)


@pytest.fixture
def session() -> Session:
    return Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)


def test_health_modes_and_own_identity(session: Session) -> None:
    snapshot = session.observe_gameplay()
    results = [
        PolicyProjector(
            load_policy(Path(f"config/observations/{name}.yaml")), "warlock"
        ).project(snapshot)
        for name in ("player", "visible-health", "hidden-health")
    ]
    enemies = [
        next(
            c
            for c in result.creatures
            if c.allegiance == "enemy" and c.currently_visible
        )
        for result in results
    ]
    assert enemies[0].health is not None and enemies[0].health.interval is not None
    assert enemies[0].health.current is None and enemies[0].health.maximum is None
    assert enemies[1].health is not None and enemies[1].health.current is not None
    assert enemies[2].health is None
    assert (
        results[0].action_details
        == results[1].action_details
        == results[2].action_details
    )
    assert [(c.creature_ref, c.allegiance) for c in results[0].creatures][:2] == [
        ("warlock", "own"),
        ("barbarian", "ally"),
    ]
    assert session.observe_gameplay() == snapshot
    with pytest.raises(FrozenInstanceError):
        results[0].creatures[0].health = None  # type: ignore[misc]


@pytest.mark.parametrize("memory", ["current_only", "last_known"])
def test_visibility_memory_reset_and_noninterference(
    session: Session, memory: str
) -> None:
    policy = policy_with(
        **{"creatures.health.disclosure.enemy": "exact", "memory.enemy": memory}
    )
    projector = PolicyProjector(policy, "warlock")
    snapshot = session.observe_gameplay()
    first = projector.project(snapshot)
    ref = next(
        c.creature_ref
        for c in first.creatures
        if c.allegiance == "enemy" and c.currently_visible
    )
    hidden = replace(
        snapshot,
        teams=tuple(
            replace(t, visible_creature_refs=t.visible_creature_refs - {ref})
            for t in snapshot.teams
        ),
    )
    observed = projector.project(hidden)
    changed = replace(
        hidden,
        creatures=tuple(
            replace(
                c,
                combat=replace(
                    c.combat, health=1, max_health=999, temporary_hit_points=99
                ),
            )
            if c.combat.creature_ref == ref
            else c
            for c in hidden.creatures
        ),
    )
    assert projector.project(changed) == observed
    row = next(c for c in observed.creatures if c.creature_ref == ref)
    assert row.knowledge == ("last_known" if memory == "last_known" else "unknown")
    assert (row.health is not None) == (memory == "last_known")
    reset = projector.project(replace(hidden, episode_id=(99, 0)))
    assert next(c for c in reset.creatures if c.creature_ref == ref).health is None


@pytest.mark.parametrize(
    "mode,value", [("exact", 7), ("presence", True), ("hidden", None)]
)
def test_temporary_health(session: Session, mode: str, value: object) -> None:
    snapshot = session.observe_gameplay()
    ref = "goblin_1"
    snapshot = replace(
        snapshot,
        creatures=tuple(
            replace(c, combat=replace(c.combat, temporary_hit_points=7))
            if c.combat.creature_ref == ref
            else c
            for c in snapshot.creatures
        ),
    )
    observation = PolicyProjector(
        policy_with(**{"creatures.temporary_health.enemy": mode}), "warlock"
    ).project(snapshot)
    assert (
        next(c for c in observation.creatures if c.creature_ref == ref).temporary_health
        == value
    )


def test_event_time_evidence_retention_and_numbering(session: Session) -> None:
    snapshot = session.observe_gameplay()
    visible = (("heroes", frozenset({"warlock", "goblin_1"})),)
    hidden = (("heroes", frozenset({"warlock"})),)
    events = tuple(
        GameplayEventObservation(
            seq=i,
            type="attack_resolved",
            creature_ref="goblin_1",
            data={
                "target_ref": "goblin_1",
                "damage": 5,
                "hit": True,
                "attack_name": "secret",
            },
            visible_by_team=visible if i % 2 else hidden,
        )
        for i in range(1, 25)
    )
    snapshot = replace(snapshot, history=events)
    projector = PolicyProjector(
        policy_with(**{"history.recent_event_limit": 10}), "warlock"
    )
    observed = projector.project(snapshot)
    assert len(observed.recent_events) == 10
    assert [e.seq for e in observed.recent_events] == list(range(3, 13))
    assert all(e.source_id is None for e in observed.recent_events)
    assert (
        next(
            c for c in observed.creatures if c.creature_ref == "goblin_1"
        ).observed_damage_total
        == 60
    )
    assert projector.project(snapshot) == observed
    for mode in ("hidden", "perceived"):
        policy = policy_with(
            **{"history.events": mode, "history.recent_event_limit": 0}
        )
        result = PolicyProjector(policy, "warlock").project(snapshot)
        assert result.recent_events == ()
        assert (
            next(
                c for c in result.creatures if c.creature_ref == "goblin_1"
            ).observed_damage_total
            == 60
        )
    with pytest.raises(ValueError, match="backwards"):
        projector.project(replace(snapshot, history=()))
