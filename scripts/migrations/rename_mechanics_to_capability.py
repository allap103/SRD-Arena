"""Rename authored ``mechanics`` fields to ``capability``.

Run without arguments to preview the affected files, then pass ``--write`` to
apply the migration. Only dictionaries whose ``mechanics`` value describes an
executable capability are changed; omission records that name a single
unsupported ``mechanic`` are deliberately outside this migration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTENT_DIR = REPOSITORY_ROOT / "content" / "system"


def migrate_document(document: object) -> tuple[object, int]:
    changes = _visit(document)
    return document, changes


def _visit(value: object) -> int:
    if isinstance(value, list):
        return sum(_visit(item) for item in value)
    if not isinstance(value, dict):
        return 0

    changes = 0
    if "mechanics" in value:
        if "capability" in value:
            raise ValueError("Document defines both 'mechanics' and 'capability'.")
        items = [
            ("capability" if key == "mechanics" else key, item)
            for key, item in value.items()
        ]
        value.clear()
        value.update(items)
        changes += 1

    return changes + sum(_visit(item) for item in value.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=DEFAULT_CONTENT_DIR,
    )
    args = parser.parse_args()

    changed_files = 0
    changed_fields = 0
    for path in sorted(args.content_dir.rglob("*.json")):
        source = path.read_text(encoding="utf-8")
        document = json.loads(source)
        _, changes = migrate_document(document)
        if not changes:
            continue
        changed_files += 1
        changed_fields += changes
        print(f"{path.relative_to(args.content_dir)}: {changes}")
        if args.write:
            migrated = source.replace('"mechanics":', '"capability":')
            if migrated.count('"capability":') - source.count('"capability":') != changes:
                raise ValueError(f"Could not safely rewrite all fields in {path}.")
            path.write_text(migrated, encoding="utf-8")

    mode = "Renamed" if args.write else "Would rename"
    print(f"{mode} {changed_fields} fields in {changed_files} files.")


if __name__ == "__main__":
    main()
