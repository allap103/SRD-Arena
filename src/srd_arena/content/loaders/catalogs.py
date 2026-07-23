from pathlib import Path

from ..schemas import CreatureSchema
from .source_data import _load_json
from .types import (
    ClassCatalog,
    PlayerCharacterCatalog,
    SubclassCatalog,
)


def load_player_characters(directory: str | Path) -> PlayerCharacterCatalog:
    player_characters_dir = Path(directory)
    if not player_characters_dir.is_dir():
        return {}
    return {
        schema.id: schema
        for schema in (
            CreatureSchema.model_validate(_load_json(path))
            for path in player_characters_dir.glob("*")
        )
    }


def load_class_blocks(directory: str | Path) -> ClassCatalog:
    catalog: ClassCatalog = {}
    class_dir = Path(directory) / "class"
    if not class_dir.is_dir():
        return catalog

    for path in class_dir.glob("class-*.json"):
        data = _load_json(path)
        feature_entries = data.get("classFeature", [])
        for class_block in data.get("class", []):
            if not isinstance(class_block, dict) or not isinstance(class_block.get("name"), str):
                continue
            class_block = {
                **class_block,
                "__classFeatureEntries": feature_entries if isinstance(feature_entries, list) else [],
            }
            source = class_block.get("source")
            source_key = source if isinstance(source, str) else None
            catalog[(class_block["name"].casefold(), source_key)] = class_block
            catalog.setdefault((class_block["name"].casefold(), None), class_block)
    return catalog


def load_subclass_blocks(directory: str | Path) -> SubclassCatalog:
    catalog: SubclassCatalog = {}
    class_dir = Path(directory) / "class"
    if not class_dir.is_dir():
        return catalog

    for path in class_dir.glob("class-*.json"):
        data = _load_json(path)
        feature_entries = data.get("subclassFeature", [])
        for subclass_block in data.get("subclass", []):
            if not isinstance(subclass_block, dict) or not isinstance(subclass_block.get("name"), str):
                continue
            subclass_block = {
                **subclass_block,
                "__subclassFeatureEntries": feature_entries if isinstance(feature_entries, list) else [],
            }
            source = subclass_block.get("source")
            source_key = source if isinstance(source, str) else None
            class_name = subclass_block.get("className")
            class_source = subclass_block.get("classSource")
            class_name_key = class_name.casefold() if isinstance(class_name, str) else None
            class_source_key = class_source if isinstance(class_source, str) else None
            key = (
                subclass_block["name"].casefold(),
                source_key,
                class_name_key,
                class_source_key,
            )
            catalog[key] = subclass_block
            catalog.setdefault(
                (subclass_block["name"].casefold(), source_key, class_name_key, None),
                subclass_block,
            )
            catalog.setdefault(
                (subclass_block["name"].casefold(), None, class_name_key, None),
                subclass_block,
            )
    return catalog


def _find_class_block(
    name: str,
    source: str | None,
    class_blocks: ClassCatalog | None,
) -> dict:
    if class_blocks is None:
        raise ValueError(f"Creature references class '{name}', but no class catalog was loaded.")
    key = (name.casefold(), source)
    if key in class_blocks:
        return class_blocks[key]
    if source is not None:
        source_key = (name.casefold(), source.upper())
        if source_key in class_blocks:
            return class_blocks[source_key]
    fallback_key = (name.casefold(), None)
    if source is None and fallback_key in class_blocks:
        return class_blocks[fallback_key]
    source_text = f"|{source}" if source else ""
    raise KeyError(f"Class '{name}{source_text}' not found.")


def _find_subclass_block(
    reference,
    subclass_blocks: SubclassCatalog | None,
    class_block: dict | None,
) -> dict:
    if subclass_blocks is None:
        raise ValueError(
            f"Creature references subclass '{reference.name}', but no subclass catalog was loaded."
        )
    class_name = (
        reference.class_name
        or (str(class_block.get("name")) if class_block is not None else None)
    )
    class_source = (
        reference.class_source
        or (
            class_block.get("source")
            if isinstance(class_block, dict)
            and isinstance(class_block.get("source"), str)
            else None
        )
    )
    for key in (
        (
            reference.name.casefold(),
            reference.source,
            class_name.casefold() if isinstance(class_name, str) else None,
            class_source,
        ),
        (
            reference.name.casefold(),
            reference.source.upper() if isinstance(reference.source, str) else None,
            class_name.casefold() if isinstance(class_name, str) else None,
            class_source.upper() if isinstance(class_source, str) else None,
        ),
        (
            reference.name.casefold(),
            None,
            class_name.casefold() if isinstance(class_name, str) else None,
            None,
        ),
    ):
        if key in subclass_blocks:
            return subclass_blocks[key]
    source_text = f"|{reference.source}" if reference.source else ""
    raise KeyError(f"Subclass '{reference.name}{source_text}' not found.")
