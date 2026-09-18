"""Bounded caches and byte indexes for selective reads of append-only reports."""

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

type Signature = tuple[str, int, int, int]


def signature(path: Path) -> Signature:
    """Identify a file revision; appends, replacements and edits invalidate caches."""
    path = path.resolve()
    try:
        stat = path.stat()
        return str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return str(path), 0, 0, 0


@dataclass(frozen=True)
class Record:
    """Locate a row without retaining its nested payload in memory."""

    offset: int
    length: int
    episode: int
    round: int = 0
    turn_actor: str = "setup"
    actor: str | None = None
    sequence: int = 0
    label: str = ""
    controller: str = ""


def _iter_lines(revision: Signature) -> Iterator[tuple[int, int, dict[str, Any]]]:
    """Stream committed records without retaining full-file text or nested data."""
    path, _, size, _ = revision
    if not size:
        return
    with Path(path).open("rb") as stream:
        number = 0
        while stream.tell() < size:
            start = stream.tell()
            line = stream.readline(size - start)
            number += 1
            if not line.endswith(b"\n"):
                break
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError(
                    f"Invalid JSON record in {path}, line {number}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected an object in {path}, line {number}")
            yield start, len(line), row


@lru_cache(maxsize=16)
def index(revision: Signature) -> tuple[Record, ...]:
    """Cache compact offsets, never full combat summaries or command snapshots."""
    return tuple(
        Record(
            offset,
            length,
            int(row.get("episode", 0)),
            int(row.get("round", 0)),
            row.get("turn_actor") or "setup",
            row.get("actor"),
            int(row.get("sequence", 0)),
            str(row.get("label", "")),
            str(row.get("controller", "")),
        )
        for offset, length, row in _iter_lines(revision)
    )


def read_record(revision: Signature, record: Record) -> dict[str, Any]:
    """Seek directly to one requested record, without reading preceding episodes."""
    with Path(revision[0]).open("rb") as stream:
        current = os.fstat(stream.fileno())
        if (
            current.st_ino != revision[1]
            or current.st_size < revision[2]
            or (current.st_size == revision[2] and current.st_mtime_ns != revision[3])
        ):
            raise ValueError("The log changed while reading; refresh records")
        stream.seek(record.offset)
        value = json.loads(stream.read(record.length))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON record; refresh if the log was replaced")
    return value


@lru_cache(maxsize=4)
def metrics(revision: Signature) -> tuple[dict[str, Any], ...]:
    """Cache metrics independently from much larger combat and trace files."""
    return tuple(row for _, _, row in _iter_lines(revision))


@lru_cache(maxsize=32)
def document(revision: Signature) -> dict[str, Any]:
    """Cache configuration and provenance by file revision."""
    if revision[2] == 0:
        return {}
    value = json.loads(Path(revision[0]).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {revision[0]}")
    return value


def lineage(run: Path, filename: str) -> tuple[tuple[Signature, int | None], ...]:
    """Resolve ancestor limits before loading the requested kind of report."""
    seen: set[Path] = set()
    result = []
    limit: int | None = None
    while True:
        run = run.resolve()
        if run in seen:
            raise ValueError("Run lineage contains a cycle")
        seen.add(run)
        result.append((signature(run / filename), limit))
        manifest = document(signature(run / "manifest.json"))
        parent = manifest.get("resume_from")
        if not parent:
            break
        boundary = int(manifest["starting_episode"]) - 1
        limit = min(limit, boundary) if limit is not None else boundary
        run = Path(parent)
    return tuple(reversed(result))


def metric_history(run: Path) -> list[dict[str, Any]]:
    """Load only scalar episode reports across the admitted lineage."""
    return [
        {**row, "source_run": str(Path(revision[0]).parent)}
        for revision, limit in lineage(run, "metrics.jsonl")
        for row in metrics(revision)
        if limit is None or row["episode"] <= limit
    ]


def summary_index(run: Path) -> list[tuple[Signature, Record]]:
    """Locate completed episodes without loading their combat payloads."""
    return [
        (revision, row)
        for revision, limit in lineage(run, "combat-summary.jsonl")
        for row in index(revision)
        if limit is None or row.episode <= limit
    ]


@lru_cache(maxsize=4)
def trace_events(revision: Signature) -> tuple[dict[str, Any], ...]:
    """Retain only event attribution for delayed casts and identifier searches."""
    return tuple(
        {
            **event,
            "boundary_sequence": row["sequence"],
            "round": row["round"],
            "turn_actor": row["turn_actor"],
        }
        for _, _, row in _iter_lines(revision)
        for event in row.get("events", [])
    )


def clear_caches() -> None:
    """Discard cached revisions when the user explicitly refreshes records."""
    for cached in (index, metrics, document, trace_events):
        cached.cache_clear()
