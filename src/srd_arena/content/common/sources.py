"""Load JSON and normalize source-aware content identifiers."""

import json
from pathlib import Path

SOURCE_PRIORITY = {
    "XPHB": 30,
    "XDMG": 30,
    "XMM": 30,
    "PHB": 20,
    "DMG": 20,
    "MM": 20,
}


def load_json(path: str | Path) -> dict[str, object]:
    """Read one UTF-8 JSON document from a content path.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory) / "record.json"
    ...     _ = path.write_text('{"name": "Goblin"}', encoding="utf-8")
    ...     load_json(path)
    {'name': 'Goblin'}
    """

    with Path(path).open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in '{path}'.")
    return payload


def slug(value: str) -> str:
    """Normalize a content label into a stable lowercase identifier fragment.

    >>> slug("Melf's Acid Arrow")
    'melfs_acid_arrow'
    """

    return value.lower().replace("'", "").replace(",", "").replace(" ", "_")
