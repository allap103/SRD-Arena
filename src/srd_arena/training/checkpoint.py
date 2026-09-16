"""Shared loading boundary for evaluation and spectator playback."""

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import torch

from srd_arena.frontends.headless.config import load_policy, policy_digest
from srd_arena.frontends.rl.encoding import encoder_manifest
from srd_arena.training.config import TrainingConfig, load_training_config
from srd_arena.training.model import MODEL_SCHEMA_ID, CandidatePolicy, select_device


@dataclass(frozen=True)
class LoadedCheckpoint:
    """A validated model and its saved experiment settings."""

    config: TrainingConfig
    model: CandidatePolicy
    device: torch.device
    completed_episodes: int = 0
    checkpoint_sha256: str = ""


def load_checkpoint(
    run_dir: Path, *, device_name: Literal["auto", "cpu", "cuda"] = "auto"
) -> LoadedCheckpoint:
    """Validate encoder/disclosure identity before loading weights for inference."""
    config = load_training_config(run_dir / "config.json")
    device = select_device(device_name)
    checkpoint_bytes = (run_dir / "policy.pt").read_bytes()
    checkpoint = torch.load(
        io.BytesIO(checkpoint_bytes), map_location="cpu", weights_only=True
    )
    policy = load_policy(Path(config.observation_config))
    if (
        checkpoint["model_schema"] != MODEL_SCHEMA_ID
        or checkpoint["encoder"] != encoder_manifest()
        or checkpoint["policy_digest"] != policy_digest(policy)
    ):
        raise ValueError("Checkpoint schema or observation policy does not match")
    model = CandidatePolicy(checkpoint["hidden_size"]).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return LoadedCheckpoint(
        config,
        model,
        device,
        checkpoint.get("completed_episodes", 0),
        hashlib.sha256(checkpoint_bytes).hexdigest(),
    )
