"""Disclosed turn context, privacy, evidence memory and numerical distinctions."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    GameplayConditionObservation,
    GameplayEventObservation,
    GameplayObservation,
    ObservationPolicy,
    PolicyProjector,
    ResourcePoolObservation,
    Session,
    SpellSlotObservation,
)
from srd_arena.engine.observability import Observability
from srd_arena.frontends.headless.config import load_policy
from srd_arena.frontends.headless.serialization import canonical_json
from srd_arena.frontends.rl.encoding import ENTITY_FEATURES, Encoder


@pytest.fixture
def snapshot() -> GameplayObservation:
    """Use a real fixed-party snapshot as the disclosure source."""
    return Session(
        EncounterCatalog().load_encounter("warlock_training"), seed=42
    ).observe_gameplay()


def projector(profile: str = "training") -> PolicyProjector:
    """Load an executable policy with its actual defaults."""
    return PolicyProjector(
        load_policy(Path(f"config/observations/{profile}.yaml")), "warlock"
    )


def test_resources_budgets_and_status_change_numeric_input(
    snapshot: GameplayObservation,
) -> None:
    """Balances and turn state are explicit, even without any action candidates."""
    p = projector()
    first = p.project(snapshot)
    encoder = Encoder(first)
    before = encoder.encode(first, ()).entities[0]
    actor = next(c for c in snapshot.creatures if c.combat.creature_ref == "warlock")
    changed = replace(
        actor,
        actions_remaining=0,
        bonus_action_available=False,
        spell_slot_spent_this_turn=True,
        concentrating_on=("hypnotic_pattern",),
        conditions=(
            GameplayConditionObservation("prone", ("private",), Observability.OBVIOUS),
        ),
        combat=replace(
            actor.combat,
            movement_remaining_feet=0,
            reaction_available=False,
            attacks_remaining=0,
            spell_slots=(SpellSlotObservation(3, 0, 2),),
            resource_pools=(
                ResourcePoolObservation("opaque", "lucky", "feature_uses", 0, 3),
            ),
        ),
    )
    second = p.project(
        replace(
            snapshot,
            creatures=tuple(changed if c is actor else c for c in snapshot.creatures),
        )
    )
    after = encoder.encode(second, ()).entities[0]
    for name, value in {
        "movement_remaining_feet": 0,
        "actions_remaining": 0,
        "bonus_action_available": 0,
        "reaction_available": 0,
        "slot_3_remaining": 0,
        "slot_3_maximum": 0.2,
        "resource_lucky_remaining": 0,
        "resource_lucky_maximum": 0.3,
        "spell_slot_spent_this_turn": 1,
        "condition_prone": 1,
        "conditions_complete": 1,
        "concentrating": 1,
        "concentrating_on_hypnotic_pattern": 1,
    }.items():
        assert after[ENTITY_FEATURES.index(name)] == value
    for name in (
        "movement_remaining_feet",
        "slot_3_remaining",
        "resource_lucky_remaining",
        "spell_slot_spent_this_turn",
        "condition_prone",
        "concentrating",
    ):
        assert before[ENTITY_FEATURES.index(name)] != after[ENTITY_FEATURES.index(name)]
    hidden = projector("minimal").project(
        replace(
            snapshot,
            creatures=tuple(changed if c is actor else c for c in snapshot.creatures),
        )
    )
    hidden_values = encoder.encode(hidden, ()).entities[0]
    for name in (
        "movement_budget_known",
        "action_economy_known",
        "resources_known",
        "conditions_known",
        "concentration_known",
    ):
        assert after[ENTITY_FEATURES.index(name)] == 1
        assert hidden_values[ENTITY_FEATURES.index(name)] == 0
    for name in (
        "movement",
        "action_economy",
        "resources",
        "conditions",
        "concentrating_on",
    ):
        assert getattr(hidden.creatures[0], name) is None


def test_private_enemy_changes_do_not_change_arrays(
    snapshot: GameplayObservation,
) -> None:
    """Seeing an opponent does not reveal resources, budgets or hidden conditions."""
    p = projector()
    view = p.project(snapshot)
    encoder = Encoder(view)
    before = encoder.encode(view, ()).entities
    enemy = next(c for c in snapshot.creatures if c.combat.creature_ref == "goblin_1")
    changed = replace(
        enemy,
        actions_remaining=17,
        spell_slot_spent_this_turn=True,
        concentrating_on=("hex",),
        conditions=(
            GameplayConditionObservation("charmed", ("secret",), Observability.HIDDEN),
        ),
        combat=replace(
            enemy.combat,
            spell_slots=(SpellSlotObservation(9, 8, 9),),
            movement_remaining_feet=999,
            resource_pools=(
                ResourcePoolObservation("x", "lucky", "feature_uses", 99, 99),
            ),
        ),
    )
    after = p.project(
        replace(
            snapshot,
            creatures=tuple(changed if c is enemy else c for c in snapshot.creatures),
        )
    )
    np.testing.assert_array_equal(before, encoder.encode(after, ()).entities)
    row = next(c for c in after.creatures if c.creature_ref == "goblin_1")
    assert row.conditions == () and row.conditions_complete is False
    assert row.resources is None
    assert row.action_economy is None
    assert row.movement is None
    assert row.concentrating_on is None


@pytest.mark.parametrize("visible", [False, True])
def test_manifested_conditions_need_visible_matching_evidence_and_reset(
    snapshot: GameplayObservation, visible: bool
) -> None:
    """Symptoms identify one active instance; stale facts never track hidden changes."""
    enemy = next(c for c in snapshot.creatures if c.combat.creature_ref == "goblin_1")
    enemy = replace(
        enemy,
        conditions=(
            GameplayConditionObservation("prone", ("p",), Observability.OBVIOUS),
            GameplayConditionObservation(
                "poisoned", ("q",), Observability.AFTER_TRIGGER
            ),
        ),
    )
    snapshot = replace(
        snapshot,
        creatures=tuple(
            enemy if c.combat.creature_ref == "goblin_1" else c
            for c in snapshot.creatures
        ),
    )
    p = projector()

    def names(value: GameplayObservation) -> tuple[str, ...] | None:
        return next(
            c for c in p.project(value).creatures if c.creature_ref == "goblin_1"
        ).conditions

    assert names(snapshot) == ("prone",)
    event = GameplayEventObservation(
        999,
        "condition_manifested",
        "goblin_1",
        data={
            "manifestation": "stinking_cloud_retching",
            "condition": "poisoned",
            "condition_id": "q",
        },
        visible_by_team=(
            ("heroes", frozenset({"goblin_1"}) if visible else frozenset()),
        ),
    )
    witnessed = replace(snapshot, history=(*snapshot.history, event))
    expected = ("prone", "poisoned") if visible else ("prone",)
    assert names(witnessed) == expected
    cleared = replace(
        witnessed,
        creatures=tuple(
            replace(c, conditions=()) if c is enemy else c for c in witnessed.creatures
        ),
    )
    unseen = replace(
        cleared,
        teams=tuple(
            replace(t, visible_creature_refs=t.visible_creature_refs - {"goblin_1"})
            for t in cleared.teams
        ),
    )
    assert names(unseen) == expected
    assert names(cleared) == ()
    assert names(replace(snapshot, episode_id=(987, 654), history=())) == ("prone",)


def test_unknown_vocabularies_and_empty_collections(
    snapshot: GameplayObservation,
) -> None:
    """Unknown semantics have buckets; known empty collections have known flags."""
    view = projector().project(snapshot)
    own = next(c for c in view.creatures if c.creature_ref == "warlock")
    assert own.resources is not None
    own = replace(
        own,
        concentrating_on=("future_spell",),
        conditions=("future_condition",),
        resources=replace(
            own.resources,
            spell_slots=(),
            class_resources=(
                ResourcePoolObservation(
                    "private-token", "future_feature", "feature_uses", 2, 4
                ),
            ),
        ),
    )
    view = replace(
        view,
        creatures=tuple(
            own if c.creature_ref == "warlock" else c for c in view.creatures
        ),
    )
    encoder = Encoder(view)
    row = encoder.encode(view, ()).entities[0]
    for key, value in {
        "condition_unknown": 1,
        "concentrating_on_unknown": 1,
        "resource_other_feature_remaining": 0.2,
        "resource_other_feature_maximum": 0.4,
        "resources_known": 1,
        "slot_3_remaining": 0,
    }.items():
        assert row[ENTITY_FEATURES.index(key)] == value
    assert own.resources is not None
    empty = replace(
        own,
        conditions=(),
        concentrating_on=(),
        resources=replace(own.resources, class_resources=()),
    )
    empty_view = replace(
        view,
        creatures=tuple(
            empty if c.creature_ref == "warlock" else c for c in view.creatures
        ),
    )
    row = encoder.encode(empty_view, ()).entities[0]
    assert row[ENTITY_FEATURES.index("conditions_known")] == 1
    assert row[ENTITY_FEATURES.index("concentration_known")] == 1
    assert row[ENTITY_FEATURES.index("concentrating")] == 0


@pytest.mark.parametrize(
    "field", ["resources", "movement", "action_economy", "concentration", "conditions"]
)
def test_enemy_private_modes_remain_rejected(field: str) -> None:
    """A YAML edit cannot opt into opponent private state in this supported slice."""
    data = projector().policy.model_dump(mode="json")
    data["creatures"][field]["enemy"] = "all" if field == "conditions" else "exact"
    policy = ObservationPolicy.model_validate_json(canonical_json(data))
    with pytest.raises(ValueError, match="unsupported"):
        policy.validate_support()
