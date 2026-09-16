"""Train a small episodic PyTorch policy on one deliberately repeated encounter."""

import argparse
import json
import math
import platform
import random
import subprocess
import sys
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
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
from srd_arena.training.diagnostics import EpisodeRecorder
from srd_arena.training.model import MODEL_SCHEMA_ID, CandidatePolicy, select_device
from srd_arena.training.progress import EpisodeProgress
from srd_arena.training.resume import capture_training_state, restore_training_state


def rollout(
    environment: ArenaEnvironment,
    model: CandidatePolicy,
    *,
    seed: int,
    mode: Literal["sample", "greedy", "random", "wait"] = "sample",
    rng: np.random.Generator | None = None,
    progress: EpisodeProgress | None = None,
    diagnostics: EpisodeRecorder | None = None,
) -> tuple[list[tuple[EncodedObservation, int]], Transition]:
    """Collect a bounded episode; all baseline choices use the filtered interface."""
    previous_diagnostic = environment.diagnostic_callback
    if diagnostics is not None:
        environment.diagnostic_callback = diagnostics.record
    previous_callback = environment.progress_callback
    if progress is not None:
        environment.progress_callback = progress.engine_progress
    try:
        started = perf_counter()
        transition = environment.reset(seed=seed)
        if progress is not None:
            progress.reset_seconds = perf_counter() - started
            progress.report("rollout", force=True)
        trajectory: list[tuple[EncodedObservation, int]] = []
        while not (transition.terminated or transition.truncated):
            if progress is not None:
                progress.report("inference")
            started = perf_counter()
            if mode == "random":
                assert rng is not None
                action = int(rng.integers(len(environment.choices)))
            elif mode == "wait":
                action = idle_action(environment.choices)
            else:
                action = model.choose(
                    transition.observation,
                    greedy=mode == "greedy",
                    report=(
                        lambda selection: diagnostics.record_choice(
                            selection, environment.choices
                        )
                    )
                    if diagnostics is not None and diagnostics.stream is not None
                    else None,
                )
            if (
                diagnostics is not None
                and diagnostics.stream is not None
                and mode in {"wait", "random"}
            ):
                diagnostics.record_choice(
                    {
                        "mode": mode,
                        "selected_index": action,
                        "selected_probability": 1 / len(environment.choices)
                        if mode == "random"
                        else None,
                        "candidate_count": len(environment.choices),
                    },
                    environment.choices,
                )
            if progress is not None:
                progress.inference_seconds += perf_counter() - started
                progress.report("engine")
            trajectory.append((transition.observation, action))
            started = perf_counter()
            transition = environment.step(
                action, expected_decision_id=transition.decision_id
            )
            if progress is not None:
                progress.environment_seconds += perf_counter() - started
        return trajectory, transition
    finally:
        environment.progress_callback = previous_callback
        environment.diagnostic_callback = previous_diagnostic


def update_policy(
    model: CandidatePolicy,
    optimizer: torch.optim.Optimizer,
    trajectory: list[tuple[EncodedObservation, int]],
    reward: float,
    entropy_coefficient: float,
    *,
    progress: EpisodeProgress | None = None,
    metrics: dict[str, float] | None = None,
) -> float:
    """Apply Monte Carlo actor/critic gradients with undiscounted terminal return.

    Every command in the episode receives the same terminal return. No command
    cost is introduced for multi-stage actions. The critic baseline is detached
    from the policy advantage; entropy is an exploration regularizer.
    """
    if metrics is not None:
        metrics.update(policy_loss=0.0, value_loss=0.0, entropy=0.0, gradient_norm=0.0)
    if not trajectory:
        return 0.0
    optimizer.zero_grad()
    total = 0.0
    for sample_index, (observation, action) in enumerate(trajectory, start=1):
        logits, value = model(observation)
        distribution = Categorical(logits=logits)
        chosen = torch.tensor(action, device=logits.device)
        advantage = reward - value.detach()
        entropy = distribution.entropy()  # type: ignore[no-untyped-call]
        loss = (
            -distribution.log_prob(chosen) * advantage  # type: ignore[no-untyped-call]
            + 0.5 * (value - reward).square()
            - entropy_coefficient * entropy
        ) / len(trajectory)
        if metrics is not None:
            metrics["policy_loss"] += float(
                (-distribution.log_prob(chosen) * advantage).detach().cpu()  # type: ignore[no-untyped-call]
            ) / len(trajectory)
            metrics["value_loss"] += float(
                (0.5 * (value - reward).square()).detach().cpu()
            ) / len(trajectory)
            metrics["entropy"] += float(entropy.detach().cpu()) / len(trajectory)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite training loss")
        loss.backward()
        total += float(loss.detach().cpu())
        if progress is not None:
            progress.optimization_progress(sample_index, len(trajectory))
    norm = torch.nn.utils.clip_grad_norm_(
        model.parameters(), 1.0, error_if_nonfinite=True
    )
    if metrics is not None:
        metrics["gradient_norm"] = float(norm.detach().cpu())
    optimizer.step()
    return total


def run_training(
    config: TrainingConfig,
    run_dir: Path,
    *,
    progress_interval: float = 2.0,
    resume_from: Path | None = None,
    trace_every: int = 0,
    tensorboard: bool = False,
) -> Path:
    """Save resolved settings, per-episode metrics, and a reloadable checkpoint."""
    if not math.isfinite(progress_interval) or progress_interval < 0:
        raise ValueError("Progress interval must be finite and nonnegative")
    if trace_every < 0:
        raise ValueError("Trace interval must be nonnegative")
    if tensorboard:
        try:
            from torch.utils.tensorboard import SummaryWriter
        except ImportError as exc:
            raise ValueError("TensorBoard requires the observability extra") from exc
    print("Initializing training environment and model...", file=sys.stderr, flush=True)
    device = select_device(config.device)
    torch.manual_seed(config.learner_seed)
    random.seed(config.learner_seed)
    np.random.seed(config.learner_seed % (2**32))
    torch.set_num_threads(1)
    model = CandidatePolicy(config.hidden_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    environment = config.environment()
    # Validate the encounter and encoder before creating output artifacts.
    environment.reset(seed=config.encounter_seed)
    policy = load_policy(Path(config.observation_config))
    completed = 0
    if resume_from is not None:
        completed = restore_training_state(
            resume_from, config, model, optimizer, device, policy_digest(policy)
        )
        print(
            f"Resuming after episode {completed}; training {config.episodes} additional episodes...",
            file=sys.stderr,
            flush=True,
        )
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
        "diagnostics": {
            "schema": "combat-diagnostics-v1",
            "trace_every": trace_every,
            "tensorboard": tensorboard,
        },
        "resume_from": str(resume_from.resolve()) if resume_from is not None else None,
        "starting_episode": completed + 1,
        "target_completed_episodes": completed + config.episodes,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    checkpoint = run_dir / "policy.pt"
    with (
        ExitStack() as outputs,
        (run_dir / "combat-summary.jsonl").open("w") as combat_stream,
        (run_dir / "metrics.jsonl").open("w") as stream,
        (run_dir / "progress.jsonl").open("w") as progress_stream,
    ):
        writer = (
            outputs.enter_context(SummaryWriter(str(run_dir / "tensorboard")))
            if tensorboard
            else None
        )
        if writer is not None:
            writer.add_text(
                "configuration", resolved.model_dump_json(indent=2), completed
            )
        wins = 0
        for episode in range(completed, completed + config.episodes):
            with ExitStack() as episode_outputs:
                trace = None
                if trace_every and (episode == 0 or (episode + 1) % trace_every == 0):
                    (run_dir / "traces").mkdir(exist_ok=True)
                    trace = episode_outputs.enter_context(
                        (run_dir / "traces" / f"episode-{episode + 1:06d}.jsonl").open(
                            "w"
                        )
                    )
                recorder = EpisodeRecorder(episode + 1, trace)
                progress = EpisodeProgress(
                    episode + 1,
                    completed + config.episodes,
                    progress_stream,
                    interval=progress_interval,
                )
                progress.report("reset", force=True)
                episode_started = perf_counter()
                trajectory, terminal = rollout(
                    environment,
                    model,
                    seed=config.encounter_seed,
                    progress=progress,
                    diagnostics=recorder,
                )
                rollout_seconds = perf_counter() - episode_started
                progress.update_total = len(trajectory)
                progress.report("update", force=True)
                update_started = perf_counter()
                learning_metrics: dict[str, float] = {}
                loss = update_policy(
                    model,
                    optimizer,
                    trajectory,
                    terminal.reward,
                    config.entropy_coefficient,
                    progress=progress,
                    metrics=learning_metrics,
                )
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                update_seconds = perf_counter() - update_started
                record = {
                    "episode": episode + 1,
                    "seed": config.encounter_seed,
                    "reward": terminal.reward,
                    "terminated": terminal.terminated,
                    "truncated": terminal.truncated,
                    "loss": loss,
                    **learning_metrics,
                    **terminal.info,
                    **progress.timings(),
                    "rollout_seconds": rollout_seconds,
                    "update_seconds": update_seconds,
                    "episode_seconds": perf_counter() - episode_started,
                }
                # Keep the most recently completed update if a later rollout fails.
                # Replace atomically so viewers never open a half-written checkpoint.
                progress.report("checkpoint", force=True)
                checkpoint_started = perf_counter()
                temporary = checkpoint.with_suffix(".tmp")
                torch.save(
                    {
                        "model_schema": MODEL_SCHEMA_ID,
                        "encoder": encoder_manifest(),
                        "policy_digest": policy_digest(policy),
                        "hidden_size": config.hidden_size,
                        "completed_episodes": episode + 1,
                        "training_state": capture_training_state(
                            config, optimizer, device
                        ),
                        "state_dict": {
                            k: v.detach().cpu() for k, v in model.state_dict().items()
                        },
                    },
                    temporary,
                )
                temporary.replace(checkpoint)
                record["checkpoint_seconds"] = perf_counter() - checkpoint_started
                record["episode_seconds"] = perf_counter() - episode_started
                line = canonical_json(record)
                stream.write(line + "\n")
                stream.flush()
                print(line, flush=True)
                summary = recorder.summary()
                summary.update(
                    reward=terminal.reward,
                    terminated=terminal.terminated,
                    truncated=terminal.truncated,
                )
                combat_stream.write(canonical_json(summary) + "\n")
                combat_stream.flush()
                wins += terminal.reward > 0
                if writer is not None:
                    for key, value in {
                        **learning_metrics,
                        "loss": loss,
                        "reward": terminal.reward,
                        "win_rate": wins / (episode - completed + 1),
                        "truncated": int(terminal.truncated),
                        "rounds": recorder.rounds,
                        "rejected_commands": terminal.info["rejected_commands"],
                        **progress.timings(),
                        "update_seconds": update_seconds,
                    }.items():
                        writer.add_scalar("train/" + key, value, episode + 1)
                    writer.flush()
                progress.report("done", force=True)
    return checkpoint


def main() -> None:
    """Run a configured experiment with optional short-run/device overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path)
    source.add_argument(
        "--resume",
        type=Path,
        help="Source run directory; restore its saved settings and training state",
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--episodes",
        type=int,
        help="Episodes to run (additional episodes when resuming)",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"))
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=2.0,
        help="Seconds between live progress reports (default: 2; 0 disables periodic reports; turn logs remain)",
    )
    parser.add_argument(
        "--trace-every",
        type=int,
        default=0,
        help="Save full combat traces every N cumulative episodes, plus episode 1; 0 saves summaries only",
    )
    parser.add_argument(
        "--tensorboard",
        action="store_true",
        help="Write TensorBoard learning metrics (requires observability extra)",
    )
    args = parser.parse_args()
    try:
        if args.resume is not None and args.episodes is None:
            raise ValueError(
                "--resume requires --episodes specifying additional episodes"
            )
        config_path = (
            args.resume / "config.json"
            if args.resume is not None
            else args.config or Path("config/training/single_encounter.yaml")
        )
        config = load_training_config(config_path)
        values = config.model_dump()
        if args.episodes is not None:
            values["episodes"] = args.episodes
        if args.device is not None:
            values["device"] = cast(Literal["auto", "cpu", "cuda"], args.device)
        config = TrainingConfig.model_validate(values)
        checkpoint = run_training(
            config,
            args.run_dir,
            progress_interval=args.progress_interval,
            resume_from=args.resume,
            trace_every=args.trace_every,
            tensorboard=args.tensorboard,
        )
        print(canonical_json({"checkpoint": str(checkpoint)}))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Training failed: {exc}\n")


if __name__ == "__main__":
    main()
