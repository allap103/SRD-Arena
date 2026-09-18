"""Numerical information boundaries, action grammar, and bounded episodes."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    AimAction,
    CastSpell,
    FilteredAction,
    PolicyProjector,
    Session,
    SpellCastOptions,
)
from srd_arena.frontends.headless.adapter import EpisodeState, EpisodeStatus
from srd_arena.frontends.rl.actions import candidates
from srd_arena.frontends.rl.encoding import ENTITY_FEATURES, Encoder
from srd_arena.frontends.rl.rewards import terminal_reward
from srd_arena.training.config import TrainingConfig, load_training_config


@pytest.fixture
def environment_config() -> TrainingConfig:
    return load_training_config(Path("config/training/single_encounter.yaml"))


def test_wait_replay_reset_and_terminal_reward(
    environment_config: TrainingConfig,
) -> None:
    environment = environment_config.environment()
    first = environment.reset(seed=42)
    first_features = first.observation.entities.copy()
    for _ in range(200):
        index = next(
            (
                i
                for i, c in enumerate(environment.choices)
                if c.kind in {"wait", "keep_initiative", "decline_d20_modifier"}
            ),
            0,
        )
        transition = environment.step(index)
        if transition.terminated or transition.truncated:
            break
        assert transition.reward == 0
    assert transition.terminated
    assert transition.info["episode_outcome"] == "win"
    components = transition.info["reward_components"]
    assert isinstance(components, dict)
    assert components["outcome"] == 1
    assert transition.reward == pytest.approx(sum(components.values()))
    assert transition.info["engine_steps"] == 62
    assert "resources" in transition.info
    assert len(environment.choices) == 0
    assert transition.observation.actions.shape[0] == 0
    with pytest.raises(RuntimeError, match="Reset"):
        environment.step(0)
    second = environment.reset(seed=42)
    np.testing.assert_array_equal(first_features, second.observation.entities)
    assert first.decision_id != second.decision_id


def test_limits_and_invalid_indices_do_not_step(
    environment_config: TrainingConfig,
) -> None:
    config = environment_config.model_copy(update={"max_decisions": 1})
    environment = config.environment()
    first = environment.reset(seed=42)
    for index in (-1, len(environment.choices), True):
        with pytest.raises(ValueError):
            environment.step(index)
    with pytest.raises(ValueError, match="Stale"):
        environment.step(0, expected_decision_id="stale")
    end = environment.step(0, expected_decision_id=first.decision_id)
    assert end.truncated and not end.terminated
    assert end.reward == 0 and end.info["decisions"] == 1
    assert end.info["truncation_reason"] == "decision_limit"


def test_automatic_limits_use_internal_clock(
    environment_config: TrainingConfig,
) -> None:
    environment = environment_config.model_copy(
        update={"max_engine_steps": 4}
    ).environment()
    transition = environment.reset(seed=42)
    while not (transition.terminated or transition.truncated):
        index = next(
            (
                i
                for i, c in enumerate(environment.choices)
                if c.kind in {"wait", "keep_initiative", "decline_d20_modifier"}
            ),
            0,
        )
        transition = environment.step(index)
    assert transition.info["engine_steps"] == 4
    assert transition.info["truncation_reason"] == "engine_step_limit"


def test_encoder_masks_hidden_values_and_stable_slots(
    environment_config: TrainingConfig,
) -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    projector = PolicyProjector(environment_config.environment().policy, "warlock")
    snapshot = session.observe_gameplay()
    observation = projector.project(snapshot)
    encoder = Encoder(observation)
    encoded = encoder.encode(observation, candidates(observation))
    hp = ENTITY_FEATURES.index("exact_health_known")
    assert encoded.entities[0, hp] == 1
    assert np.all(encoded.entities[2 : len(encoder.refs), hp] == 0)
    assert encoded.entity_mask.sum() == len(snapshot.creatures)
    assert not np.any(encoded.entities[len(snapshot.creatures) :])
    reordered = encoder.encode(
        replace(observation, creatures=tuple(reversed(observation.creatures))),
        candidates(observation),
    )
    np.testing.assert_array_equal(encoded.entities, reordered.entities)
    hidden = replace(
        snapshot,
        teams=tuple(
            replace(t, visible_creature_refs=t.visible_creature_refs - {"goblin_1"})
            for t in snapshot.teams
        ),
    )
    before = encoder.encode(projector.project(hidden), ())
    changed = replace(
        hidden,
        creatures=tuple(
            replace(c, combat=replace(c.combat, health=1, max_health=987))
            if c.combat.creature_ref == "goblin_1"
            else c
            for c in hidden.creatures
        ),
    )
    after = encoder.encode(projector.project(changed), ())
    np.testing.assert_array_equal(before.entities, after.entities)
    with pytest.raises(ValueError, match="capacity"):
        Encoder(observation, max_entities=1)


def test_aim_and_allocation_candidates_use_public_parameters(
    environment_config: TrainingConfig,
) -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    observation = PolicyProjector(
        environment_config.environment().policy, "warlock"
    ).project(session.observe_gameplay())
    aim = FilteredAction(
        "test-aim", "spell", "warlock", None, None, True, "available", "aim"
    )
    choices = candidates(replace(observation, action_details=(aim,)))
    assert len(choices) == observation.grid.width * observation.grid.height
    assert all(isinstance(c.command, AimAction) for c in choices)
    assert choices[-1].aim == (11.0, 8.0)
    with pytest.raises(ValueError, match="candidate"):
        candidates(replace(observation, action_details=(aim,)), maximum=1)
    allocation = replace(
        aim,
        required_configuration=None,
        spell_cast=SpellCastOptions(
            ("warlock",), (), 1, False, False, True, 3, (("warlock", 3),)
        ),
    )
    base = candidates(replace(observation, action_details=(allocation,)))[0]
    from srd_arena.frontends.rl.spell_candidates import preparation_choices

    choices = preparation_choices(base, maximum=100)
    assert [c.amount for c in choices] == [1, 2, 3]
    assert all(isinstance(c.command, CastSpell) for c in choices)


def test_original_outcome_only_baseline() -> None:
    from srd_arena.engine.api import EncounterTerminationReason
    from srd_arena.frontends.headless.adapter import EpisodeTruncationReason

    win = EpisodeStatus(
        EpisodeState.TERMINATED,
        EncounterTerminationReason.LAST_TEAM_STANDING,
        winning_team_id="heroes",
    )
    assert terminal_reward(win, "heroes") == 1
    assert terminal_reward(win, "goblins") == -1
    draw = EpisodeStatus(
        EpisodeState.TERMINATED, EncounterTerminationReason.ALL_TEAMS_DEFEATED
    )
    assert terminal_reward(draw, "heroes") == 0
    truncated = EpisodeStatus(
        EpisodeState.TRUNCATED, truncation_reason=EpisodeTruncationReason.STEP_LIMIT
    )
    assert terminal_reward(truncated, "heroes") == 0
    assert terminal_reward(EpisodeStatus(EpisodeState.ACTIVE), "heroes") == 0
