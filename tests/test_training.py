"""Policy optimization, checkpoint replay, and explicit device contracts."""

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from srd_arena.frontends.rl.encoding import EncodedObservation
from srd_arena.frontends.rl.environment import ArenaEnvironment, Transition
from srd_arena.training.config import load_training_config
from srd_arena.training.evaluate import evaluate
from srd_arena.training.model import CandidatePolicy, select_device
from srd_arena.training.progress import EpisodeProgress
from srd_arena.training.train import run_training, update_policy


def test_policy_update_improves_rewarded_choice_and_changes_parameters() -> None:
    torch.manual_seed(7)
    config = load_training_config(Path("config/training/single_encounter.yaml"))
    observation = config.environment().reset(seed=42).observation
    model = CandidatePolicy(8)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.05)
    before = model(observation)[0].softmax(dim=0).detach()
    state = {k: v.clone() for k, v in model.state_dict().items()}
    loss = update_policy(model, optimizer, [(observation, 0)], 1.0, 0.0)
    after = model(observation)[0].softmax(dim=0).detach()
    assert np.isfinite(loss)
    assert after[0] > before[0]
    assert any(not torch.equal(v, state[k]) for k, v in model.state_dict().items())


def test_masked_actions_never_selected() -> None:
    from dataclasses import replace

    config = load_training_config(Path("config/training/single_encounter.yaml"))
    observation = config.environment().reset(seed=42).observation
    mask = np.zeros(len(observation.actions), dtype=np.bool_)
    mask[0] = True
    observation = replace(observation, action_mask=mask)
    model = CandidatePolicy(8)
    assert all(model.choose(observation) == 0 for _ in range(20))
    logits, _ = model(observation)
    assert torch.isneginf(logits[1:]).all()


def test_training_checkpoint_reloads_and_replays(tmp_path: Path) -> None:
    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={"episodes": 2, "max_decisions": 5, "hidden_size": 8, "device": "cpu"}
    )
    run = tmp_path / "run"
    checkpoint = run_training(config, run)
    assert checkpoint.exists()
    assert len((run / "metrics.jsonl").read_text().splitlines()) == 2
    first = evaluate(run, episodes=1, device_name="cpu", seed=123)
    assert evaluate(run, episodes=1, device_name="cpu", seed=123) == first
    assert first["episodes"] == 1
    with pytest.raises(FileExistsError):
        run_training(config, run)
    assert (run / "observation-policy.json").exists()
    progress = [
        json.loads(line) for line in (run / "progress.jsonl").read_text().splitlines()
    ]
    phases = [r["phase"] for r in progress if r["event"] == "progress"]
    assert phases.count("reset") == phases.count("done") == 2
    assert "update" in phases and "checkpoint" in phases
    metrics = [
        json.loads(line) for line in (run / "metrics.jsonl").read_text().splitlines()
    ]
    for record in metrics:
        assert (
            record["episode_seconds"]
            >= record["rollout_seconds"] + record["update_seconds"]
        )
        assert record["reset_seconds"] >= 0 and record["inference_seconds"] >= 0
        assert record["environment_seconds"] >= 0 and record["checkpoint_seconds"] >= 0


def test_explicit_cuda_does_not_silently_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert select_device("auto").type == "cpu"
    assert select_device("cpu").type == "cpu"
    with pytest.raises(RuntimeError, match="CUDA was requested"):
        select_device("cuda")


def test_completed_update_survives_a_later_rollout_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import srd_arena.training.train as training

    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={"episodes": 2, "max_decisions": 1, "hidden_size": 8, "device": "cpu"}
    )
    original = training.rollout
    calls = 0

    def failing_rollout(
        environment: ArenaEnvironment,
        model: CandidatePolicy,
        *,
        seed: int,
        progress: EpisodeProgress | None = None,
    ) -> tuple[list[tuple[EncodedObservation, int]], Transition]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated rollout failure")
        return original(environment, model, seed=seed, progress=progress)

    monkeypatch.setattr(training, "rollout", failing_rollout)
    with pytest.raises(RuntimeError, match="simulated rollout failure"):
        run_training(config, tmp_path / "interrupted")
    checkpoint = torch.load(tmp_path / "interrupted/policy.pt", weights_only=True)
    assert checkpoint["completed_episodes"] == 1
    assert not (tmp_path / "interrupted/policy.tmp").exists()
    assert len((tmp_path / "interrupted/metrics.jsonl").read_text().splitlines()) == 1
