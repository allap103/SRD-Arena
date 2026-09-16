"""Spectator diagnostics preserve play and record scripted actions and events."""

import io
import json
from pathlib import Path

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
