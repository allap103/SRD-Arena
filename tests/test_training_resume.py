"""Continuing training preserves updates, sampling state and source artifacts."""

import json
from pathlib import Path
from typing import Any

import pytest
import torch

from srd_arena.training.config import TrainingConfig, load_training_config
from srd_arena.training.train import run_training


def small_config(episodes: int = 1) -> TrainingConfig:
    """Use real engine observations with short, inexpensive rollouts."""
    return load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={
            "episodes": episodes,
            "max_decisions": 3,
            "hidden_size": 8,
            "device": "cpu",
        }
    )


def assert_identical(left: Any, right: Any) -> None:
    """Compare nested optimizer and RNG state, including exact tensor contents."""
    if isinstance(left, torch.Tensor):
        assert torch.equal(left, right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            assert_identical(left[key], right[key])
    elif isinstance(left, (tuple, list)):
        assert type(left) is type(right) and len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            assert_identical(a, b)
    else:
        assert left == right


@pytest.mark.parametrize(
    "device",
    [
        "cpu",
        pytest.param(
            "cuda",
            marks=pytest.mark.skipif(
                not torch.cuda.is_available(), reason="CUDA unavailable"
            ),
        ),
    ],
)
def test_split_training_matches_uninterrupted_training(
    tmp_path: Path, device: str
) -> None:
    continuous = run_training(
        small_config(2).model_copy(update={"device": device}),
        tmp_path / "continuous",
        progress_interval=0,
    )
    parent = tmp_path / "parent"
    run_training(
        small_config().model_copy(update={"device": device}),
        parent,
        progress_interval=0,
    )
    before = {p.name: p.read_bytes() for p in parent.iterdir()}
    # Load the saved policy/settings exactly as the resume CLI does.
    config = load_training_config(parent / "config.json")
    child = tmp_path / "child"
    resumed = run_training(config, child, resume_from=parent, progress_interval=0)
    assert before == {p.name: p.read_bytes() for p in parent.iterdir()}
    assert_identical(
        torch.load(continuous, weights_only=True),
        torch.load(resumed, weights_only=True),
    )
    expected = json.loads(
        (tmp_path / "continuous/metrics.jsonl").read_text().splitlines()[1]
    )
    actual = json.loads((child / "metrics.jsonl").read_text())
    assert {k: v for k, v in actual.items() if not k.endswith("_seconds")} == {
        k: v for k, v in expected.items() if not k.endswith("_seconds")
    }
    manifest = json.loads((child / "manifest.json").read_text())
    assert manifest["resume_from"] == str(parent.resolve())
    assert manifest["starting_episode"] == manifest["target_completed_episodes"] == 2
    progress = [
        json.loads(line) for line in (child / "progress.jsonl").read_text().splitlines()
    ]
    assert all(record["episode"] == 2 for record in progress)
    # A resumed run can itself be resumed, without depending on its ancestors.
    third = run_training(
        config, tmp_path / "third", resume_from=child, progress_interval=0
    )
    assert torch.load(third, weights_only=True)["completed_episodes"] == 3


@pytest.mark.parametrize(
    "damage",
    [
        "legacy",
        "schema",
        "policy",
        "device",
        "rng",
        "settings",
        "reward_schema",
        "weights",
    ],
)
def test_invalid_resume_does_not_create_output(tmp_path: Path, damage: str) -> None:
    parent = tmp_path / "parent"
    checkpoint_path = run_training(small_config(), parent, progress_interval=0)
    checkpoint = torch.load(checkpoint_path, weights_only=True)
    config = small_config()
    if damage == "legacy":
        del checkpoint["training_state"]
    elif damage == "schema":
        checkpoint["encoder"] = {}
    elif damage == "policy":
        checkpoint["policy_digest"] = "changed"
    elif damage == "device":
        checkpoint["training_state"]["device_type"] = "cuda"
    elif damage == "rng":
        del checkpoint["training_state"]["torch_rng"]
    elif damage == "reward_schema":
        checkpoint["training_state"]["reward_schema"] = "terminal-team-outcome-v1"
    elif damage == "weights":
        config = config.model_copy(
            update={"reward": config.reward.model_copy(update={"victory_health": 0.2})}
        )
    else:
        checkpoint["training_state"]["settings"]["learning_rate"] = 0.5
    torch.save(checkpoint, checkpoint_path)
    before = checkpoint_path.read_bytes()
    child = tmp_path / "child"
    with pytest.raises(ValueError):
        run_training(config, child, resume_from=parent, progress_interval=0)
    assert not child.exists()
    assert checkpoint_path.read_bytes() == before


def test_resume_cli_requires_explicit_additional_episodes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from srd_arena.training.train import main

    monkeypatch.setattr(
        "sys.argv", ["train", "--resume", "missing", "--run-dir", "unused"]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "additional episodes" in capsys.readouterr().err


def test_old_inference_config_retains_outcome_only_scoring(tmp_path: Path) -> None:
    from srd_arena.training.checkpoint import load_checkpoint

    run = tmp_path / "legacy"
    run_training(small_config(), run, progress_interval=0)
    config = json.loads((run / "config.json").read_text())
    del config["reward"]
    (run / "config.json").write_text(json.dumps(config))
    loaded = load_checkpoint(run, device_name="cpu")
    assert loaded.config.reward.party_member_down == 0
    assert loaded.config.reward.victory_health == 0
    assert loaded.config.reward.victory_spell_slots == 0
    assert loaded.config.reward.victory_class_resources == 0
    assert loaded.config.reward.win == 1
    assert loaded.config.reward.loss == -1
