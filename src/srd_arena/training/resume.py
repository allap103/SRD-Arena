"""Training state saved at completed episode boundaries, separate from inference."""

import random
from pathlib import Path
from typing import Any

import numpy as np
import torch

from srd_arena.engine.api import FILTERED_OBSERVATION_SCHEMA_ID
from srd_arena.frontends.rl.actions import ACTION_SCHEMA_ID
from srd_arena.frontends.rl.encoding import encoder_manifest
from srd_arena.frontends.rl.rewards import REWARD_SCHEMA_ID
from srd_arena.training.config import TrainingConfig
from srd_arena.training.model import MODEL_SCHEMA_ID, CandidatePolicy

TRAINING_STATE_SCHEMA = "episodic-training-state-v1"


def training_settings(config: TrainingConfig) -> dict[str, Any]:
    """Compare learning semantics independently of paths and run length."""
    return config.model_dump(exclude={"episodes", "device", "observation_config"})


def capture_training_state(
    config: TrainingConfig,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> dict[str, Any]:
    """Capture optimizer and RNGs using types accepted by weights_only loading."""
    numpy_state = np.random.get_state()
    return {
        "schema": TRAINING_STATE_SCHEMA,
        "settings": training_settings(config),
        "device_type": device.type,
        "observation_schema": FILTERED_OBSERVATION_SCHEMA_ID,
        "action_schema": ACTION_SCHEMA_ID,
        "reward_schema": REWARD_SCHEMA_ID,
        "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state(device) if device.type == "cuda" else None,
        "python_rng": random.getstate(),
        "numpy_rng": (
            numpy_state[0],
            numpy_state[1].tolist(),
            *numpy_state[2:],
        ),
    }


def restore_training_state(
    source: Path,
    config: TrainingConfig,
    model: CandidatePolicy,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    policy_digest: str,
) -> int:
    """Validate and restore one boundary; never modify the source run."""
    checkpoint = torch.load(source / "policy.pt", map_location="cpu", weights_only=True)
    state = checkpoint.get("training_state")
    if not isinstance(state, dict) or state.get("schema") != TRAINING_STATE_SCHEMA:
        raise ValueError(
            "Checkpoint has no supported training state; older inference-only "
            "checkpoints cannot resume training"
        )
    if state.get("reward_schema") != REWARD_SCHEMA_ID:
        raise ValueError(
            "Reward schema differs from this checkpoint; --resume cannot change "
            "the training objective. Start a new run with the new reward settings."
        )
    if (
        checkpoint.get("model_schema") != MODEL_SCHEMA_ID
        or checkpoint.get("encoder") != encoder_manifest()
        or checkpoint.get("policy_digest") != policy_digest
        or checkpoint.get("hidden_size") != config.hidden_size
        or state.get("settings") != training_settings(config)
        or state.get("observation_schema") != FILTERED_OBSERVATION_SCHEMA_ID
        or state.get("action_schema") != ACTION_SCHEMA_ID
    ):
        raise ValueError(
            "Resume configuration (including reward weights), schema or observation policy does not match"
        )
    if state.get("device_type") != device.type:
        raise ValueError(
            "Resume requires the same device type (CPU/CUDA) as the checkpoint"
        )
    completed = checkpoint.get("completed_episodes")
    if type(completed) is not int or completed < 1:
        raise ValueError("Checkpoint has an invalid completed episode count")
    try:
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(state["optimizer"])
        torch.set_rng_state(state["torch_rng"])
        if device.type == "cuda":
            torch.cuda.set_rng_state(state["cuda_rng"], device)
        random.setstate(state["python_rng"])
        numpy_state = state["numpy_rng"]
        np.random.set_state(
            (
                numpy_state[0],
                np.asarray(numpy_state[1], dtype=np.uint32),
                *numpy_state[2:],
            )
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ValueError(f"Invalid training checkpoint state: {exc}") from exc
    return completed
