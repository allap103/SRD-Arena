"""Evaluation reports use frozen weights, recorded seeds and all controllers."""

import json
from pathlib import Path

import pytest

from srd_arena.training.config import load_training_config
from srd_arena.training.evaluate import evaluate, main
from srd_arena.training.train import run_training


def test_comparison_writes_inspectable_reports_without_modifying_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={"episodes": 1, "max_decisions": 2, "hidden_size": 8, "device": "cpu"}
    )
    source = tmp_path / "source"
    checkpoint = run_training(config, source, progress_interval=0)
    original = checkpoint.read_bytes()
    output = tmp_path / "comparison"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate",
            "--run-dir",
            str(source),
            "--output-dir",
            str(output),
            "--compare",
            "--episodes",
            "2",
            "--device",
            "cpu",
            "--trace-every",
            "1",
        ],
    )
    main()
    comparison = json.loads((output / "comparison.json").read_text())
    reports = comparison["controllers"]
    assert [r["mode"] for r in reports] == ["sample", "greedy", "random", "wait"]
    assert len({r["checkpoint_sha256"] for r in reports}) == 1
    assert checkpoint.read_bytes() == original
    for report in reports:
        assert report["checkpoint_completed_episodes"] == 1
        rows = [
            json.loads(line)
            for line in (output / report["mode"] / "metrics.jsonl")
            .read_text()
            .splitlines()
        ]
        assert [r["sampling_seed"] for r in rows] == [123, 124]
        assert all(r["encounter_seed"] == config.encounter_seed for r in rows)
        assert len(list((output / report["mode"] / "traces").glob("*.jsonl"))) == 2
        assert (
            report["wins"]
            + report["losses"]
            + report["draws"]
            + report["truncated_episodes"]
            == 2
        )
    repeated = evaluate(source, episodes=2, device_name="cpu", mode="sample")
    assert repeated == reports[0]
    assert reports[-1]["creature_means"]["warlock"]["spell_cast_events"] == 0


def test_evaluation_rejects_trace_without_output() -> None:
    with pytest.raises(ValueError, match="output-dir"):
        evaluate(Path("unused"), trace_every=1)
