"""Read local diagnostic artifacts, including incomplete live files and lineage."""

import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Ignore an unfinished final line while surfacing corrupt complete records."""
    if not path.exists():
        return []
    content = path.read_text()
    lines = content.splitlines(keepends=True)
    result = []
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1 and not line.endswith("\n"):
                break
            raise ValueError(
                f"Invalid JSON record in {path}, line {index + 1}"
            ) from None
        if not isinstance(row, dict):
            raise ValueError(f"Expected an object in {path}, line {index + 1}")
        result.append(row)
    return result


def history(run: Path, filename: str) -> list[dict[str, Any]]:
    """Follow one parent chain, excluding episodes trained after the branch point."""
    visited: set[Path] = set()
    segments: list[list[dict[str, Any]]] = []
    limit: int | None = None
    while True:
        run = run.resolve()
        if run in visited:
            raise ValueError("Run lineage contains a cycle")
        visited.add(run)
        segments.append(
            [
                {**row, "source_run": str(run)}
                for row in read_jsonl(run / filename)
                if limit is None or row["episode"] <= limit
            ]
        )
        manifest_path = run / "manifest.json"
        if not manifest_path.exists():
            break
        manifest = json.loads(manifest_path.read_text())
        parent = manifest.get("resume_from")
        if not parent:
            break
        limit = (
            min(limit, manifest["starting_episode"] - 1)
            if limit is not None
            else manifest["starting_episode"] - 1
        )
        run = Path(parent)
    return [row for segment in reversed(segments) for row in segment]


def action_totals(
    summaries: list[dict[str, Any]], actors: list[str]
) -> list[dict[str, Any]]:
    """Aggregate semantically grouped commands over the selected episodes."""
    counts: dict[tuple[str, str, str], int] = {}
    for summary in summaries:
        for row in summary["actions"]:
            if row["actor"] not in actors:
                continue
            key = (row["actor"], row["action"], row["result"])
            counts[key] = counts.get(key, 0) + row["count"]
    return [
        {"actor": a, "action": action, "result": result, "count": n}
        for (a, action, result), n in sorted(counts.items())
    ]
