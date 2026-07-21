import json
from pathlib import Path

SOURCE_PRIORITY = {
    "XPHB": 30,
    "XDMG": 30,
    "PHB": 20,
    "DMG": 20,
}


def _load_json(path: str | Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _slug(value: str) -> str:
    return value.lower().replace("'", "").replace(",", "").replace(" ", "_")
