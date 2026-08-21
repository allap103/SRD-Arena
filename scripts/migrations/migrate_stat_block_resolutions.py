"""Migrate flat stat-block resolutions into capability envelopes.

Run with ``--write`` after reviewing the dry-run report. The migration is
idempotent and rejects unfamiliar mechanics shapes instead of guessing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MONSTERS_DIR = REPOSITORY_ROOT / "content" / "system" / "monsters"


def migrate_document(document: object) -> tuple[object, list[str]]:
    changes: list[str] = []
    _visit(document, changes, path="$.")
    return document, changes


def _visit(value: object, changes: list[str], *, path: str) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _visit(item, changes, path=f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return

    mechanics = value.get("mechanics")
    if isinstance(mechanics, dict):
        action_name = str(value.get("name", "<unnamed>"))
        migrated = _migrate_mechanics(mechanics)
        if migrated is not mechanics:
            value["mechanics"] = migrated
            changes.append(f"{path} {action_name}: {mechanics['type']}")

    for key, item in value.items():
        _visit(item, changes, path=f"{path}{key}.")


def _migrate_mechanics(mechanics: dict[str, Any]) -> dict[str, Any]:
    mechanics_type = mechanics.get("type")
    if mechanics_type == "saving_throw":
        return _migrate_saving_throw(mechanics)
    if mechanics_type == "automatic":
        return _migrate_automatic(mechanics)
    return mechanics


def _migrate_saving_throw(mechanics: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "type",
        "target",
        "ability",
        "dc",
        "failure",
        "success",
        "success_damage",
        "always",
        "resource",
    }
    _reject_unknown(mechanics, allowed)
    resolution: dict[str, Any] = {
        "type": "saving_throw",
        "ability": mechanics["ability"],
        "difficulty": {"type": "fixed", "value": mechanics["dc"]},
        "failure": mechanics["failure"],
        "success": {"effects": mechanics.get("success", [])},
        "always": {"effects": mechanics.get("always", [])},
        "success_damage": mechanics.get("success_damage", "none"),
    }
    return _capability_envelope(mechanics, resolution)


def _migrate_automatic(mechanics: dict[str, Any]) -> dict[str, Any]:
    allowed = {"type", "target", "outcome", "resource"}
    _reject_unknown(mechanics, allowed)
    resolution = {
        "type": "automatic",
        "outcome": mechanics["outcome"],
    }
    return _capability_envelope(mechanics, resolution)


def _capability_envelope(
    mechanics: dict[str, Any],
    resolution: dict[str, Any],
) -> dict[str, Any]:
    migrated = {
        "type": "capability",
        "target": mechanics["target"],
        "resolution": resolution,
    }
    if "resource" in mechanics:
        migrated["resource"] = mechanics["resource"]
    return migrated


def _reject_unknown(mechanics: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(mechanics) - allowed
    if unknown:
        raise ValueError(
            f"Cannot migrate {mechanics.get('type')} mechanics with unknown keys: "
            f"{', '.join(sorted(unknown))}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--monsters-dir",
        type=Path,
        default=DEFAULT_MONSTERS_DIR,
    )
    args = parser.parse_args()

    changed_files = 0
    changed_actions = 0
    for path in sorted(args.monsters_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        migrated, changes = migrate_document(document)
        if not changes:
            continue
        changed_files += 1
        changed_actions += len(changes)
        print(f"{path.name}: {', '.join(changes)}")
        if args.write:
            path.write_text(
                json.dumps(migrated, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    mode = "Migrated" if args.write else "Would migrate"
    print(f"{mode} {changed_actions} actions in {changed_files} files.")


if __name__ == "__main__":
    main()
