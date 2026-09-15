"""Train a small episodic PyTorch policy on one deliberately repeated encounter."""

import argparse
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Literal, cast

import numpy as np
import torch
from torch.distributions import Categorical

from srd_arena.engine.api import FILTERED_OBSERVATION_SCHEMA_ID
from srd_arena.frontends.headless.config import load_policy, policy_digest
from srd_arena.frontends.headless.serialization import canonical_json
from srd_arena.frontends.rl.actions import ACTION_SCHEMA_ID
from srd_arena.frontends.rl.encoding import EncodedObservation, encoder_manifest
from srd_arena.frontends.rl.environment import ArenaEnvironment, Transition
from srd_arena.frontends.rl.rewards import REWARD_SCHEMA_ID
from srd_arena.training.baselines import idle_action
from srd_arena.training.config import TrainingConfig, load_training_config
from srd_arena.training.model import MODEL_SCHEMA_ID, CandidatePolicy, select_device


def rollout(
    environment: ArenaEnvironment,
    model: CandidatePolicy,
    *,
    seed: int,
    mode: Literal["sample", "greedy", "random", "wait"] = "sample",
    rng: np.random.Generator | None = None,
) -> tuple[list[tuple[EncodedObservation, int]], Transition]:
    """Collect a bounded episode; all baseline choices use the filtered interface."""
    transition = environment.reset(seed=seed)
    trajectory: list[tuple[EncodedObservation, int]] = []
    while not (transition.terminated or transition.truncated):
        if mode == "random":
            assert rng is not None
            action = int(rng.integers(len(environment.choices)))
        elif mode == "wait":
            action = idle_action(environment.choices)
        else:
            action = model.choose(transition.observation, greedy=mode == "greedy")
        trajectory.append((transition.observation, action))
        transition = environment.step(
            action, expected_decision_id=transition.decision_id
        )
    return trajectory, transition


def update_policy(
    model: CandidatePolicy,
    optimizer: torch.optim.Optimizer,
    trajectory: list[tuple[EncodedObservation, int]],
    reward: float,
    entropy_coefficient: float,
) -> float:
    """Apply Monte Carlo actor/critic gradients with undiscounted terminal return.

    Every command in the episode receives the same terminal return. No command
    cost is introduced for multi-stage actions. The critic baseline is detached
    from the policy advantage; entropy is an exploration regularizer.
    """
    if not trajectory:
        return 0.0
    optimizer.zero_grad()
    total = 0.0
    for observation, action in trajectory:
        logits, value = model(observation)
        distribution = Categorical(logits=logits)
        chosen = torch.tensor(action, device=logits.device)
        advantage = reward - value.detach()
        loss = (
            -distribution.log_prob(chosen) * advantage  # type: ignore[no-untyped-call]
            + 0.5 * (value - reward).square()
            - entropy_coefficient * distribution.entropy()  # type: ignore[no-untyped-call]
        ) / len(trajectory)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite training loss")
        loss.backward()
        total += float(loss.detach().cpu())
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
    optimizer.step()
    return total


def run_training(config: TrainingConfig, run_dir: Path) -> Path:
    """Save resolved settings, per-episode metrics, and a reloadable checkpoint."""
    device = select_device(config.device)
    torch.manual_seed(config.learner_seed)
    torch.set_num_threads(1)
    model = CandidatePolicy(config.hidden_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    environment = config.environment()
    # Validate the encounter and encoder before creating output artifacts.
    environment.reset(seed=config.encounter_seed)
    policy = load_policy(Path(config.observation_config))
    run_dir.mkdir(parents=True, exist_ok=False)
    # Freeze the exact policy next to the experiment so evaluation does not
    # silently pick up edits to the source YAML file.
    saved_policy = run_dir / "observation-policy.json"
    saved_policy.write_text(canonical_json(policy) + "\n")
    resolved = config.model_copy(
        update={"observation_config": "observation-policy.json"}
    )
    (run_dir / "config.json").write_text(resolved.model_dump_json(indent=2) + "\n")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=False
    ).stdout.strip()
    manifest = {
        "package_version": version("srd-arena"),
        "git_revision": revision,
        "working_tree_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip()
        ),
        "python_version": platform.python_version(),
        "torch_version": str(torch.__version__),
        "numpy_version": np.__version__,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "policy_digest": policy_digest(policy),
        "observation_schema": FILTERED_OBSERVATION_SCHEMA_ID,
        "action_schema": ACTION_SCHEMA_ID,
        "reward_schema": REWARD_SCHEMA_ID,
        "model_schema": MODEL_SCHEMA_ID,
        "encoder": encoder_manifest(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    checkpoint = run_dir / "policy.pt"
    with (run_dir / "metrics.jsonl").open("w") as stream:
        for episode in range(config.episodes):
            trajectory, terminal = rollout(
                environment, model, seed=config.encounter_seed
            )
            loss = update_policy(
                model,
                optimizer,
                trajectory,
                terminal.reward,
                config.entropy_coefficient,
            )
            record = {
                "episode": episode + 1,
                "seed": config.encounter_seed,
                "reward": terminal.reward,
                "terminated": terminal.terminated,
                "truncated": terminal.truncated,
                "loss": loss,
                **terminal.info,
            }
            line = canonical_json(record)
            stream.write(line + "\n")
            stream.flush()
            print(line, flush=True)
            # Keep the most recently completed update if a later rollout fails.
            # Replace atomically so viewers never open a half-written checkpoint.
            temporary = checkpoint.with_suffix(".tmp")
            torch.save(
                {
                    "model_schema": MODEL_SCHEMA_ID,
                    "encoder": encoder_manifest(),
                    "policy_digest": policy_digest(policy),
                    "hidden_size": config.hidden_size,
                    "completed_episodes": episode + 1,
                    "state_dict": {
                        k: v.detach().cpu() for k, v in model.state_dict().items()
                    },
                },
                temporary,
            )
            temporary.replace(checkpoint)
    return checkpoint


def main() -> None:
    """Run a configured experiment with optional short-run/device overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("config/training/single_encounter.yaml")
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"))
    args = parser.parse_args()
    try:
        config = load_training_config(args.config)
        values = config.model_dump()
        if args.episodes is not None:
            values["episodes"] = args.episodes
        if args.device is not None:
            values["device"] = cast(Literal["auto", "cpu", "cuda"], args.device)
        config = TrainingConfig.model_validate(values)
        checkpoint = run_training(config, args.run_dir)
        print(canonical_json({"checkpoint": str(checkpoint)}))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Training failed: {exc}\n")


if __name__ == "__main__":
    main()
