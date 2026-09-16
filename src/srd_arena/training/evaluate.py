"""Evaluate a checkpoint with reproducible controllers and local combat reports."""

import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import torch

from srd_arena.frontends.headless.serialization import canonical_json
from srd_arena.training.checkpoint import load_checkpoint
from srd_arena.training.diagnostics import EpisodeRecorder
from srd_arena.training.train import rollout

EVALUATION_SCHEMA = "fixed-encounter-evaluation-v1"


def evaluate(
    run_dir: Path,
    *,
    episodes: int = 5,
    device_name: Literal["auto", "cpu", "cuda"] = "auto",
    mode: Literal["sample", "greedy", "random", "wait"] = "sample",
    seed: int = 123,
    output_dir: Path | None = None,
    trace_every: int = 0,
    tensorboard: bool = False,
    encounter_seed: int | None = None,
) -> dict[str, Any]:
    """Use fixed combat seed and independent seed+i controller seeds per episode.

    Reports compare behavior on one encounter, not generalization. Saved reports
    include episode seeds, resource outcomes and per-creature command summaries.
    """
    if (
        episodes < 1
        or seed < 0
        or trace_every < 0
        or (encounter_seed is not None and encounter_seed < 0)
    ):
        raise ValueError(
            "Episodes must be positive; seeds and trace interval nonnegative"
        )
    if (tensorboard or trace_every) and output_dir is None:
        raise ValueError("Traces and TensorBoard require --output-dir")
    if tensorboard:
        try:
            from torch.utils.tensorboard import SummaryWriter
        except ImportError as exc:
            raise ValueError("TensorBoard requires the observability extra") from exc
    loaded = load_checkpoint(run_dir, device_name=device_name)
    config, model, device = loaded.config, loaded.model, loaded.device
    combat_seed = config.encounter_seed if encounter_seed is None else encounter_seed
    torch.set_num_threads(1)
    environment = config.environment()
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Any]] = {}
    with ExitStack() as outputs:
        metrics_stream = combat_stream = writer = None
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=False)
            metrics_stream = outputs.enter_context(
                (output_dir / "metrics.jsonl").open("w")
            )
            combat_stream = outputs.enter_context(
                (output_dir / "combat-summary.jsonl").open("w")
            )
            (output_dir / "config.json").write_text(
                config.model_dump_json(indent=2) + "\n"
            )
            # Hash the weights file to identify the exact evaluated checkpoint,
            # even if the source trainer later atomically replaces it.
            manifest = {
                "kind": "evaluation",
                "schema": EVALUATION_SCHEMA,
                "checkpoint_run": str(run_dir.resolve()),
                "mode": mode,
                "sampling_seed": seed,
                "encounter_seed": combat_seed,
                "episodes": episodes,
                "trace_every": trace_every,
                "checkpoint_sha256": loaded.checkpoint_sha256,
                "checkpoint_completed_episodes": loaded.completed_episodes,
                "source_manifest": json.loads((run_dir / "manifest.json").read_text()),
            }
            (output_dir / "manifest.json").write_text(canonical_json(manifest) + "\n")
            if tensorboard:
                writer = outputs.enter_context(
                    SummaryWriter(str(output_dir / "tensorboard"))
                )
        for episode in range(1, episodes + 1):
            torch.manual_seed(seed + episode - 1)
            rng = np.random.default_rng(seed + episode - 1)
            with ExitStack() as episode_outputs:
                stream = None
                if (
                    output_dir is not None
                    and trace_every
                    and (episode == 1 or episode % trace_every == 0)
                ):
                    (output_dir / "traces").mkdir(exist_ok=True)
                    stream = episode_outputs.enter_context(
                        (output_dir / "traces" / f"episode-{episode:06d}.jsonl").open(
                            "w"
                        )
                    )
                recorder = EpisodeRecorder(episode, stream)
                _, terminal = rollout(
                    environment,
                    model,
                    seed=combat_seed,
                    mode=mode,
                    rng=rng,
                    diagnostics=recorder,
                )
                summary = recorder.summary()
                summary.update(
                    reward=terminal.reward,
                    terminated=terminal.terminated,
                    truncated=terminal.truncated,
                )
                row = {
                    "episode": episode,
                    "sampling_seed": seed + episode - 1,
                    "encounter_seed": combat_seed,
                    "reward": terminal.reward,
                    "terminated": terminal.terminated,
                    "truncated": terminal.truncated,
                    "rounds_reached": recorder.rounds,
                    **terminal.info,
                }
                rows.append(row)
                for ref, values in summary["creatures"].items():
                    target = totals.setdefault(
                        ref, {"name": values["name"], "team": values["team"]}
                    )
                    for key, value in values.items():
                        if isinstance(value, (float, int)):
                            target[key] = target.get(key, 0) + value
                if metrics_stream is not None and combat_stream is not None:
                    metrics_stream.write(canonical_json(row) + "\n")
                    combat_stream.write(canonical_json(summary) + "\n")
                    metrics_stream.flush()
                    combat_stream.flush()
                if writer is not None:
                    for key in (
                        "reward",
                        "truncated",
                        "rounds_reached",
                        "rejected_commands",
                    ):
                        writer.add_scalar("eval/" + key, row[key], episode)
                    writer.flush()
    report = {
        "schema": EVALUATION_SCHEMA,
        "mode": mode,
        "episodes": episodes,
        "encounter_seed": combat_seed,
        "sampling_seed": seed,
        "device": str(device),
        "checkpoint_completed_episodes": loaded.completed_episodes,
        "checkpoint_sha256": loaded.checkpoint_sha256,
        "win_rate": sum(r["reward"] > 0 for r in rows) / episodes,
        "wins": sum(r["reward"] > 0 for r in rows),
        "losses": sum(r["reward"] < 0 for r in rows),
        "draws": sum(r["terminated"] and r["reward"] == 0 for r in rows),
        "mean_reward": sum(r["reward"] for r in rows) / episodes,
        "truncated_episodes": sum(r["truncated"] for r in rows),
        "rejected_commands": sum(r["rejected_commands"] for r in rows),
        "mean_rounds": sum(r["rounds_reached"] for r in rows) / episodes,
        "mean_decisions": sum(r["decisions"] for r in rows) / episodes,
        "mean_engine_steps": sum(r["engine_steps"] for r in rows) / episodes,
        "creature_means": {
            ref: {
                k: v / episodes if isinstance(v, (float, int)) else v
                for k, v in values.items()
            }
            for ref, values in totals.items()
        },
    }
    if output_dir is not None:
        (output_dir / "evaluation.json").write_text(canonical_json(report) + "\n")
    return report


def main() -> None:
    """Compare learned and baseline controllers using the same evaluation budget."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--mode", choices=("sample", "greedy", "random", "wait"), default="sample"
    )
    modes.add_argument(
        "--compare",
        action="store_true",
        help="Evaluate sample, greedy, random and wait controllers",
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--encounter-seed", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--trace-every", type=int, default=0)
    parser.add_argument("--tensorboard", action="store_true")
    args = parser.parse_args()
    try:
        if args.compare:
            if args.output_dir is None:
                raise ValueError("--compare requires a new --output-dir")
            # Copy the exact source checkpoint/config into the report so every
            # controller evaluates the same weights, even during live training.
            import shutil

            args.output_dir.mkdir(parents=True, exist_ok=False)
            frozen = args.output_dir / "checkpoint"
            frozen.mkdir()
            for name in (
                "policy.pt",
                "config.json",
                "observation-policy.json",
                "manifest.json",
            ):
                shutil.copyfile(args.run_dir / name, frozen / name)
            reports = [
                evaluate(
                    frozen,
                    episodes=args.episodes,
                    device_name=args.device,
                    mode=cast(Literal["sample", "greedy", "random", "wait"], mode),
                    seed=args.seed,
                    encounter_seed=args.encounter_seed,
                    output_dir=args.output_dir / mode,
                    trace_every=args.trace_every,
                    tensorboard=args.tensorboard,
                )
                for mode in ("sample", "greedy", "random", "wait")
            ]
            report: dict[str, Any] = {
                "schema": EVALUATION_SCHEMA,
                "controllers": reports,
            }
            (args.output_dir / "comparison.json").write_text(
                canonical_json(report) + "\n"
            )
        else:
            report = evaluate(
                args.run_dir,
                episodes=args.episodes,
                device_name=args.device,
                mode=args.mode,
                seed=args.seed,
                output_dir=args.output_dir,
                trace_every=args.trace_every,
                tensorboard=args.tensorboard,
                encounter_seed=args.encounter_seed,
            )
        print(canonical_json(report))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")


if __name__ == "__main__":
    main()
