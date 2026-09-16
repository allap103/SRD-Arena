"""Local viewer supports lineage, live partial files and real turn inspection."""

import json
from pathlib import Path

import pytest

from srd_arena.training.inspection_data import history, read_jsonl


def test_lineage_excludes_parent_episodes_after_branch_and_reads_partial_lines(
    tmp_path: Path,
) -> None:
    parent, child = tmp_path / "parent", tmp_path / "child"
    parent.mkdir()
    child.mkdir()
    (parent / "metrics.jsonl").write_text(
        '{"episode":1}\n{"episode":2}\n{"episode":3}\n'
    )
    (child / "manifest.json").write_text(
        json.dumps({"resume_from": str(parent), "starting_episode": 2})
    )
    (child / "metrics.jsonl").write_text('{"episode":2}\n{"episode":')
    assert [r["episode"] for r in history(child, "metrics.jsonl")] == [1, 2]
    (child / "metrics.jsonl").write_text("invalid\n")
    with pytest.raises(ValueError, match="line 1"):
        read_jsonl(child / "metrics.jsonl")
    (child / "metrics.jsonl").write_text("")
    (parent / "manifest.json").write_text(
        json.dumps({"resume_from": str(child), "starting_episode": 2})
    )
    with pytest.raises(ValueError, match="cycle"):
        history(child, "metrics.jsonl")


def test_inspector_renders_real_episode_and_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    testing = pytest.importorskip("streamlit.testing.v1")
    from srd_arena.training.config import load_training_config
    from srd_arena.training.train import run_training

    config = load_training_config(
        Path("config/training/single_encounter.yaml")
    ).model_copy(
        update={"episodes": 1, "max_decisions": 3, "hidden_size": 8, "device": "cpu"}
    )
    run_training(config, tmp_path / "run", trace_every=1, progress_interval=0)
    monkeypatch.setattr("sys.argv", ["inspector", "--runs-dir", str(tmp_path)])
    app = testing.AppTest.from_file(
        Path("src/srd_arena/training/inspector.py").resolve()
    ).run(timeout=30)
    assert not app.exception
    assert not app.error
    assert app.dataframe
    turns = next(s for s in app.selectbox if s.label == "Turn")
    turns.select_index(len(turns.options) - 1).run(timeout=30)
    assert not app.exception
    assert any("accepted" in e.label for e in app.expander)
