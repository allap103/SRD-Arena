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
    """Read one UTF-8 JSON document from a content path."""

    with Path(path).open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in '{path}'.")
    return payload


def slug(value: str) -> str:
    """Normalize a content label into a stable lowercase identifier fragment."""

    return value.lower().replace("'", "").replace(",", "").replace(" ", "_")
