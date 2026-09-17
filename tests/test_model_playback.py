"""Paced watching preserves training semantics and keeps spectator data separate."""

from pathlib import Path

import numpy as np
import pytest
import torch

from srd_arena.training.checkpoint import LoadedCheckpoint
from srd_arena.training.config import load_training_config
from srd_arena.training.model import CandidatePolicy
from srd_arena.training.playback import ModelPlayback
from srd_arena.training.train import rollout


def checkpoint() -> LoadedCheckpoint:
    """Construct a small CPU model with short deterministic episode limits."""
    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(update={"device": "cpu", "hidden_size": 8, "max_decisions": 8})
    torch.manual_seed(7)
    return LoadedCheckpoint(config, CandidatePolicy(8).eval(), torch.device("cpu"))


def test_paced_playback_matches_evaluation_and_restarts() -> None:
    loaded = checkpoint()
    driver = ModelPlayback(loaded, sampling_seed=123)
    first = driver.transition.observation.entities.copy()
    first_decision = driver.transition.decision_id
    history_sequences: list[int] = []
    for _ in range(200):
        before_steps = int(str(driver.transition.info["engine_steps"]))
        update = driver.advance()
        assert update is not None
        after_steps = int(str(driver.transition.info["engine_steps"]))
        assert after_steps - before_steps in (0, 1)
        history_sequences.extend(e.seq for e in update.events)
        if driver.finished:
            break
    assert driver.finished
    assert driver.advance() is None
    assert len(set(history_sequences)) == len(history_sequences)
    final = driver.transition
    torch.manual_seed(123)
    _, evaluated = rollout(loaded.config.environment(), loaded.model, seed=42)
    assert final.info == evaluated.info
    assert final.reward == evaluated.reward
    driver.reset()
    assert not driver.finished
    assert driver.transition.decision_id != first_decision
    np.testing.assert_array_equal(first, driver.transition.observation.entities)
    torch.manual_seed(123)
    _, repeated = rollout(loaded.config.environment(), loaded.model, seed=42)
    assert repeated.info == final.info


def test_model_receives_only_encoded_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from srd_arena.frontends.rl.encoding import EncodedObservation

    loaded = checkpoint()
    seen = []

    def choose(observation: EncodedObservation, *, greedy: bool = False) -> int:
        assert isinstance(observation, EncodedObservation)
        assert not hasattr(observation, "game")
        seen.append(observation)
        return 0

    monkeypatch.setattr(loaded.model, "choose", choose)
    driver = ModelPlayback(loaded)
    viewer = driver.observe()
    assert viewer.encounter is not None
    assert viewer.encounter.creature("goblin_1").health > 0
    driver.advance()
    assert len(seen) == 1


def test_spectator_presenter_refuses_mutation() -> None:
    from srd_arena.frontends.gui.presenter import GamePresenter

    driver = ModelPlayback(checkpoint())
    presenter = GamePresenter(None, observe=driver.observe)
    initial = driver.observe()
    with pytest.raises(RuntimeError, match="Spectator"):
        presenter.select_action(initial.scene.action_details[0].id)
    with pytest.raises(RuntimeError, match="Spectator"):
        presenter.advance_one_automatic_action()
    assert driver.observe() == initial


def test_playback_labels_an_empty_cast_as_resolved_without_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from srd_arena.frontends.rl.encoding import EncodedObservation

    loaded = checkpoint()
    driver = ModelPlayback(loaded)
    chosen_spell = False

    def choose(observation: EncodedObservation, *, greedy: bool = False) -> int:
        nonlocal chosen_spell
        for index, candidate in enumerate(driver.environment.choices):
            if (
                candidate.spell is not None
                and candidate.spell.spell_id == "hypnotic_pattern"
                and candidate.affected_refs == ()
                and candidate.aim is not None
            ):
                chosen_spell = True
                return index
        return 0

    monkeypatch.setattr(loaded.model, "choose", choose)
    for _ in range(100):
        update = driver.advance()
        assert update is not None
        if chosen_spell:
            label = update.selected_choice_text
            assert label is not None
            assert "Model attempt: Cast Hypnotic Pattern" in label
            assert "cast resolved — no immediate effect" in label
            assert any(e.type == "spell_cast" for e in update.events)
            break
    assert chosen_spell
