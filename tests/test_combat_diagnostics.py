"""Spectator diagnostics preserve play and record scripted actions and events."""

import io
import json
from pathlib import Path

import pytest
import torch

from srd_arena.training.config import load_training_config
from srd_arena.training.diagnostics import EpisodeRecorder
from srd_arena.training.model import CandidatePolicy
from srd_arena.training.train import rollout


def test_recording_preserves_rollout_and_covers_scripted_combatants() -> None:
    config = load_training_config(Path("config/training/goblin_pressure.yaml"))
    model = CandidatePolicy(8)
    torch.set_num_threads(1)
    stream = io.StringIO()
    recorder = EpisodeRecorder(1, stream)
    plain, outcome = rollout(config.environment(), model, seed=42, mode="wait")
    environment = config.environment()
    logged, recorded_outcome = rollout(
        environment, model, seed=42, mode="wait", diagnostics=recorder
    )
    assert outcome.info == recorded_outcome.info
    assert outcome.reward == recorded_outcome.reward
    assert len(plain) == len(logged)
    for (a, choice), (b, logged_choice) in zip(plain, logged, strict=True):
        assert choice == logged_choice
        for name in ("global_features", "entities", "actions", "action_mask"):
            assert (getattr(a, name) == getattr(b, name)).all()
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert rows[0]["controller"] == "initial"
    assert {"model", "scripted"} <= {r["controller"] for r in rows}
    assert any(r["actor"].startswith("goblin") for r in rows if r["actor"])
    seqs = [e["seq"] for r in rows for e in r["events"]]
    assert seqs == sorted(set(seqs))
    assert recorder.summary()["creatures"]["warlock"]["wait_commands"] > 0
    assert sum(x["count"] for x in recorder.summary()["actions"]) == len(rows) - 1
    assert environment.diagnostic_callback is None


def test_policy_and_training_are_identical_with_detailed_logging(
    tmp_path: Path,
) -> None:
    event_module = pytest.importorskip(
        "tensorboard.backend.event_processing.event_accumulator"
    )

    from srd_arena.training.train import run_training

    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={"episodes": 2, "max_decisions": 3, "hidden_size": 8, "device": "cpu"}
    )
    plain = run_training(config, tmp_path / "plain", progress_interval=0)
    logged = run_training(
        config,
        tmp_path / "logged",
        progress_interval=0,
        trace_every=1,
        tensorboard=True,
    )
    a = torch.load(plain, weights_only=True)
    b = torch.load(logged, weights_only=True)
    for key, value in a["state_dict"].items():
        assert torch.equal(value, b["state_dict"][key])
    assert torch.equal(
        a["training_state"]["torch_rng"], b["training_state"]["torch_rng"]
    )
    records = [
        json.loads(line)
        for line in (logged.parent / "metrics.jsonl").read_text().splitlines()
    ]
    for record in records:
        assert (
            abs(
                record["loss"]
                - (
                    record["policy_loss"]
                    + record["value_loss"]
                    - config.entropy_coefficient * record["entropy"]
                )
            )
            < 1e-6
        )
    events = event_module.EventAccumulator(str(logged.parent / "tensorboard")).Reload()
    assert [event.step for event in events.Scalars("train/value_loss")] == [1, 2]
    traces = sorted((logged.parent / "traces").glob("*.jsonl"))
    assert len(traces) == 2
    rows = [json.loads(line) for line in traces[0].read_text().splitlines()]
    decisions = [r["policy"] for r in rows if r["controller"] == "model"]
    assert decisions and all(0 < d["selected_probability"] <= 1 for d in decisions)
    assert all(d["top_choices"] for d in decisions)
