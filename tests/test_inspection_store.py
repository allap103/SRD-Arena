"""Selective report loading stays fresh and bounded on large histories."""

import json
from pathlib import Path
from typing import Any

import pytest

from srd_arena.training.inspection_store import (
    clear_caches,
    index,
    metric_history,
    read_record,
    signature,
    summary_index,
)
from srd_arena.training.inspector_widgets import chart_data


def test_indexes_reuse_unchanged_files_and_refresh_after_append(tmp_path: Path) -> None:
    path = tmp_path / "combat-summary.jsonl"
    path.write_text('{"episode":1,"payload":"first"}\n{"episode":')
    old = signature(path)
    rows = index(old)
    assert len(rows) == 1
    assert index(old) is rows
    with path.open("a") as stream:
        stream.write('2,"payload":"second"}\n')
    current = signature(path)
    updated = index(current)
    assert [r.episode for r in updated] == [1, 2]
    assert read_record(current, updated[1])["payload"] == "second"
    assert read_record(old, rows[0])["payload"] == "first"
    path.write_text('{"episode":3}\n')
    assert [r.episode for r in index(signature(path))] == [3]
    with pytest.raises(ValueError, match="changed"):
        read_record(old, rows[0])
    path.write_text("invalid\n")
    with pytest.raises(ValueError, match="line 1"):
        index(signature(path))


def test_lineage_limits_apply_to_metrics_and_selective_summaries(
    tmp_path: Path,
) -> None:
    parent, child = tmp_path / "parent", tmp_path / "child"
    parent.mkdir()
    child.mkdir()
    for name in ("metrics.jsonl", "combat-summary.jsonl"):
        (parent / name).write_text('{"episode":1}\n{"episode":2}\n{"episode":3}\n')
        (child / name).write_text('{"episode":2}\n')
    (child / "manifest.json").write_text(
        json.dumps({"resume_from": str(parent), "starting_episode": 2})
    )
    assert [r["episode"] for r in metric_history(child)] == [1, 2]
    assert [r.episode for _, r in summary_index(child)] == [1, 2]
    (parent / "manifest.json").write_text(
        json.dumps({"resume_from": str(child), "starting_episode": 1})
    )
    with pytest.raises(ValueError, match="cycle"):
        summary_index(child)


def test_chart_smoothing_precedes_sampling_and_preserves_endpoints() -> None:
    rows = [{"episode": i, "value": i} for i in range(2500)]
    data = chart_data(rows, ["value"], 50)
    assert len(data["episode"]) == 1000
    assert data["episode"][0] == 0 and data["episode"][-1] == 2499
    assert data["value"][0] == 0
    assert data["value"][-1] == pytest.approx(sum(range(2450, 2500)) / 50)
    assert chart_data([{"episode": 1}, {"episode": 2, "value": 4}], ["value"], 2)[
        "value"
    ] == [None, 4]


def test_learning_and_tables_do_not_open_combat_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.testing.v1 import AppTest

    run = tmp_path / "large"
    run.mkdir()
    (run / "metrics.jsonl").write_text(
        "".join(
            json.dumps({"episode": i, "reward": 1, "episode_outcome": "win"}) + "\n"
            for i in range(1, 2501)
        )
    )
    # These would fail immediately if unrelated pages loaded them.
    (run / "combat-summary.jsonl").write_text("invalid\n")
    (run / "config.json").write_text("invalid")
    monkeypatch.setattr("sys.argv", ["inspector", "--runs-dir", str(tmp_path)])
    clear_caches()
    app = AppTest.from_file(Path("src/srd_arena/training/inspector.py").resolve()).run(
        timeout=30
    )
    assert not app.exception and not app.error and not app.dataframe
    app.switch_page("inspector_pages/table.py").run(timeout=30)
    assert not app.exception and not app.error
    assert len(app.dataframe[0].value) == 50
    assert app.dataframe[0].value.iloc[0]["episode"] == 2500
    next(n for n in app.number_input if n.label == "Table page").set_value(2).run(
        timeout=30
    )
    assert len(app.dataframe[0].value) == 50
    assert app.dataframe[0].value.iloc[0]["episode"] == 2450
    with (run / "metrics.jsonl").open("a") as stream:
        stream.write('{"episode":2501,"reward":1,"episode_outcome":"win"}\n')
    next(b for b in app.button if b.label == "Refresh records").click().run(timeout=30)
    next(n for n in app.number_input if n.label == "Table page").set_value(1).run(
        timeout=30
    )
    assert app.dataframe[0].value.iloc[0]["episode"] == 2501


def test_turn_with_many_commands_renders_only_selected_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.testing.v1 import AppTest

    run = tmp_path / "trace"
    (run / "traces").mkdir(parents=True)
    (run / "metrics.jsonl").write_text("")
    rows: list[dict[str, Any]] = [
        {
            "episode": 1,
            "round": 1,
            "turn_actor": "warlock",
            "actor": "warlock",
            "sequence": i,
            "label": "Move",
            "kind": "move",
            "controller": "model",
            "command": {"i": i},
            "action_id": f"move-{i}",
            "decision_id": f"d-{i}",
            "decision_kind": "turn",
            "command_seconds": 0.1,
            "rejection": None,
            "policy": None,
            "events": [],
            "before": {"warlock": {"health": 48}},
            "after": {"warlock": {"health": 48}},
        }
        for i in range(120)
    ]
    (run / "traces/episode-000001.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    monkeypatch.setattr("sys.argv", ["inspector", "--runs-dir", str(tmp_path)])
    app = AppTest.from_file(Path("src/srd_arena/training/inspector.py").resolve()).run(
        timeout=30
    )
    app.switch_page("inspector_pages/episodes.py").run(timeout=30)
    assert not app.exception and not app.error
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == 50
    assert len(app.json) == 2  # One metadata panel and one command, not 120 of each.
    next(s for s in app.selectbox if s.label == "Command").select("#119").run(
        timeout=30
    )
    assert json.loads(app.json[-1].value) == {"i": 119}
    next(t for t in app.toggle if t.label == "Show before / after").set_value(True).run(
        timeout=30
    )
    assert not app.exception and len(app.dataframe) == 3
