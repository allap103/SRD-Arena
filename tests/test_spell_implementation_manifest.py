import json
from collections import Counter
from pathlib import Path

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import SpellSchema, load_spell_catalog

PROJECT_ROOT = Path(__file__).parents[1]
MANIFEST_PATH = PROJECT_ROOT / "docs" / "spell_implementation_manifest.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _assignments(manifest: dict[str, object]) -> list[str]:
    batches = manifest["batches"]
    assert isinstance(batches, list)
    return [spell for batch in batches for spell in batch["spells"]]


def test_manifest_assigns_every_active_spell_exactly_once() -> None:
    manifest = _manifest()
    assignments = _assignments(manifest)
    counts = Counter(assignments)
    duplicates = sorted(spell for spell, count in counts.items() if count > 1)
    active = sorted(
        spell.public_name for spell in load_spell_catalog(SYSTEM_CONTENT_ROOT)
    )

    assert duplicates == []
    assert sorted(assignments) == active


def test_manifest_excludes_unsupported_spells() -> None:
    assignments = set(_assignments(_manifest()))
    unsupported_directory = SYSTEM_CONTENT_ROOT / "spells" / "unsupported"
    unsupported = {
        SpellSchema.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        ).public_name
        for path in unsupported_directory.glob("*.json")
    }

    assert assignments.isdisjoint(unsupported)


def test_manifest_batches_are_stable_and_internally_sorted() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == 1
    batches = manifest["batches"]
    assert isinstance(batches, list)

    batch_ids = [batch["id"] for batch in batches]
    assert len(batch_ids) == len(set(batch_ids))
    assert batch_ids == [
        "1A", "1B", "1C",
        "2A", "2B", "2C",
        "3A", "3B", "3C",
        "4A", "4B", "4C",
        "5A", "5B",
        "6A", "6B",
        "7A", "7B", "7C",
        "8A", "8B", "8C", "8D",
    ]
    for batch in batches:
        assert batch["spells"] == sorted(batch["spells"])
        expected_status = (
            "committed"
            if batch["wave"] == 1 or batch["id"] == "2A"
            else "provisional"
        )
        assert batch["status"] == expected_status
