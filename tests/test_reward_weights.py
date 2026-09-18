"""Weighted terminal rewards preserve outcomes and count party falls once."""

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    EncounterTerminationReason,
    GameplayEventObservation,
    GameplayObservation,
    Session,
)
from srd_arena.frontends.headless.adapter import (
    EpisodeState,
    EpisodeStatus,
    EpisodeTruncationReason,
)
from srd_arena.frontends.rl.rewards import EpisodeReward, RewardWeights
from srd_arena.training.config import TrainingConfig, load_training_config


def initial() -> GameplayObservation:
    """Use real party, slot and class-resource DTOs from the fixed encounter."""
    return Session(
        EncounterCatalog().load_encounter("warlock_training"), seed=42
    ).observe_gameplay()


def finished(winner: str | None) -> EpisodeStatus:
    """Build a rules-completed episode with an explicit winner or draw."""
    return EpisodeStatus(
        EpisodeState.TERMINATED,
        termination_reason=EncounterTerminationReason.LAST_TEAM_STANDING
        if winner
        else EncounterTerminationReason.ALL_TEAMS_DEFEATED,
        winning_team_id=winner,
    )


def test_weighted_preservation_is_normalized_and_victory_only() -> None:
    snapshot = initial()
    weights = RewardWeights(
        victory_health=0.2, victory_spell_slots=0.3, victory_class_resources=0.4
    )
    tracker = EpisodeReward(snapshot, "heroes", weights)
    # All pools and health start full; each family is capped at its own weight.
    terms = tracker.components(finished("heroes"), snapshot)
    assert terms == {
        "outcome": 1.0,
        "party_member_down": 0.0,
        "victory_health": 0.2,
        "victory_spell_slots": 0.3,
        "victory_class_resources": 0.4,
    }
    spent = replace(
        snapshot,
        creatures=tuple(
            replace(
                c,
                combat=replace(
                    c.combat,
                    health=0,
                    spell_slots=tuple(
                        replace(s, remaining=0) for s in c.combat.spell_slots
                    ),
                    resource_pools=tuple(
                        replace(p, remaining=0) for p in c.combat.resource_pools
                    ),
                ),
            )
            if c.combat.team_id == "heroes"
            else c
            for c in snapshot.creatures
        ),
    )
    tracker.observe(spent)
    terms = tracker.components(finished("heroes"), spent)
    assert (
        terms["victory_health"]
        == terms["victory_spell_slots"]
        == terms["victory_class_resources"]
        == 0
    )
    assert terms["party_member_down"] == -0.2
    for status in (
        finished("goblins"),
        finished(None),
        EpisodeStatus(
            EpisodeState.TRUNCATED, truncation_reason=EpisodeTruncationReason.STEP_LIMIT
        ),
    ):
        terms = tracker.components(status, snapshot)
        assert (
            terms["victory_health"]
            == terms["victory_spell_slots"]
            == terms["victory_class_resources"]
            == 0
        )
        assert terms["party_member_down"] == -0.2
    assert (
        sum(tracker.components(EpisodeStatus(EpisodeState.ACTIVE), spent).values()) == 0
    )


def test_fall_is_counted_once_even_if_recovered_between_snapshots() -> None:
    snapshot = initial()
    tracker = EpisodeReward(snapshot, "heroes", RewardWeights())
    seq = snapshot.history[-1].seq + 1 if snapshot.history else 1
    events = tuple(
        GameplayEventObservation(
            seq + i, "creature_defeated", actor, None, f"action-{i}", {}
        )
        for i, actor in enumerate(("barbarian", "goblin_1", "barbarian"))
    )
    recovered = replace(snapshot, history=(*snapshot.history, *events))
    tracker.observe(recovered)
    tracker.observe(recovered)
    assert tracker.fallen == {"barbarian"}
    assert (
        tracker.components(finished("heroes"), recovered)["party_member_down"] == -0.1
    )
    assert EpisodeReward(snapshot, "heroes", RewardWeights()).fallen == set()


def test_absent_resource_pools_do_not_earn_a_bonus() -> None:
    snapshot = initial()
    snapshot = replace(
        snapshot,
        creatures=tuple(
            replace(c, combat=replace(c.combat, spell_slots=(), resource_pools=()))
            for c in snapshot.creatures
        ),
    )
    tracker = EpisodeReward(
        snapshot,
        "heroes",
        RewardWeights(victory_spell_slots=0.3, victory_class_resources=0.4),
    )
    terms = tracker.components(finished("heroes"), snapshot)
    assert terms["victory_spell_slots"] == terms["victory_class_resources"] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"victory_health": -1.0},
        {"party_member_down": 0.1},
        {"win": -1.0},
        {"loss": 1.0},
        {"victory_health": float("nan")},
        {"draw": float("inf")},
        {"victory_health": "0.1"},
        {"unknown": 0.1},
    ],
)
def test_invalid_weights_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RewardWeights.model_validate(values)


def test_training_yaml_round_trips_weights(tmp_path: Path) -> None:
    config = load_training_config(Path("config/training/goblin_pressure.yaml"))
    assert config.reward == RewardWeights()
    changed = config.model_dump()
    changed["reward"]["victory_spell_slots"] = 0.02
    parsed = TrainingConfig.model_validate(changed)
    saved = tmp_path / "config.json"
    saved.write_text(parsed.model_dump_json())
    assert load_training_config(saved).reward.victory_spell_slots == 0.02
    assert parsed.environment().reward_weights == parsed.reward


def test_partial_health_and_slot_capacity_use_fractions() -> None:
    snapshot = initial()
    partial = replace(
        snapshot,
        creatures=tuple(
            replace(
                c,
                combat=replace(
                    c.combat,
                    health=c.combat.max_health // 2,
                    spell_slots=tuple(
                        replace(s, remaining=s.maximum // 2)
                        for s in c.combat.spell_slots
                    ),
                ),
            )
            for c in snapshot.creatures
        ),
    )
    tracker = EpisodeReward(snapshot, "heroes", RewardWeights(victory_spell_slots=0.2))
    terms = tracker.components(finished("heroes"), partial)
    party = [c.combat for c in partial.creatures if c.combat.team_id == "heroes"]
    assert terms["victory_health"] == pytest.approx(
        0.1 * sum(c.health for c in party) / sum(c.max_health for c in party)
    )
    assert terms["victory_spell_slots"] == pytest.approx(0.1)
