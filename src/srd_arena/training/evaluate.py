"""Replay a saved experiment using a learned, random, or waiting controller."""

import argparse
from pathlib import Path
from typing import Literal

import numpy as np
import torch

from srd_arena.frontends.headless.serialization import canonical_json
from srd_arena.training.checkpoint import load_checkpoint
from srd_arena.training.train import rollout


def evaluate(
    run_dir: Path,
    *,
    episodes: int = 5,
    device_name: Literal["auto", "cpu", "cuda"] = "auto",
    mode: Literal["sample", "greedy", "random", "wait"] = "sample",
    seed: int = 123,
) -> dict[str, object]:
    """Evaluate on the saved encounter seed; this is explicitly an overfit check."""
    if episodes < 1 or seed < 0:
        raise ValueError("Episodes must be positive and learner seed nonnegative")
    loaded = load_checkpoint(run_dir, device_name=device_name)
    config, model, device = loaded.config, loaded.model, loaded.device
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    environment = config.environment()
    rng = np.random.default_rng(seed)
    rewards = []
    truncated = rejected = 0
    for _ in range(episodes):
        _, terminal = rollout(
            environment, model, seed=config.encounter_seed, mode=mode, rng=rng
        )
        rewards.append(terminal.reward)
        truncated += terminal.truncated
        rejected += int(str(terminal.info["rejected_commands"]))
    return {
        "mode": mode,
        "episodes": episodes,
        "encounter_seed": config.encounter_seed,
        "sampling_seed": seed,
        "device": str(device),
        "win_rate": sum(r > 0 for r in rewards) / episodes,
        "mean_reward": sum(rewards) / episodes,
        "truncated_episodes": truncated,
        "rejected_commands": rejected,
    }


def main() -> None:
    """Evaluate a checkpoint with explicit device and policy/baseline selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--mode", choices=("sample", "greedy", "random", "wait"), default="sample"
    )
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()
    try:
        print(
            canonical_json(
                evaluate(
                    args.run_dir,
                    episodes=args.episodes,
                    device_name=args.device,
                    mode=args.mode,
                    seed=args.seed,
                )
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")


if __name__ == "__main__":
    main()
