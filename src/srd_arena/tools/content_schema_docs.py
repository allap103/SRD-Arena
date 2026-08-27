"""Generate navigable documentation from authored-content Pydantic models."""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import erdantic
from json_schema_for_humans.generate import (  # type: ignore[import-untyped]
    generate_from_filename,
)
from json_schema_for_humans.generation_configuration import (  # type: ignore[import-untyped]
    GenerationConfiguration,
)
from pydantic import BaseModel, TypeAdapter

from srd_arena.content.character_options.classes.schema import ClassFileSchema
from srd_arena.content.creatures.schema import CreatureSchema
from srd_arena.content.creatures.stat_block_schema import (
    BestiaryActionSchema,
    BestiaryCapabilitySchema,
    BestiaryMonsterSchema,
)
from srd_arena.content.encounters.schema import EncounterDefinitionSchema
from srd_arena.content.equipment.schema import ItemSchema
from srd_arena.content.spells.capability import SpellCapabilitySchema
from srd_arena.content.spells.implementation import SpellImplementationSchema
from srd_arena.content.spells.schema import SpellSchema

DEFAULT_OUTPUT = Path("build/content-schema-docs")


@dataclass(frozen=True)
class SchemaDocument:
    """One bounded view of the content schema."""

    slug: str
    title: str
    description: str
    schema_type: Any
    diagram_models: tuple[type[BaseModel], ...] = ()
    diagram_terminals: tuple[type[BaseModel], ...] = ()


SCHEMA_DOCUMENTS = (
    SchemaDocument(
        slug="spells",
        title="Spells",
        description=(
            "Spell metadata and its links to implementation status and executable "
            "capabilities."
        ),
        schema_type=SpellSchema,
        diagram_models=(SpellSchema,),
        diagram_terminals=(SpellCapabilitySchema, SpellImplementationSchema),
    ),
    SchemaDocument(
        slug="spell-capabilities",
        title="Spell capabilities",
        description=(
            "Targeting, resolution, scaling, requirements, and outcome triggers "
            "available to authored spells."
        ),
        schema_type=SpellCapabilitySchema,
    ),
    SchemaDocument(
        slug="bestiary",
        title="Bestiary stat blocks",
        description=(
            "Monster statistics and the action sections that grant executable "
            "capabilities."
        ),
        schema_type=BestiaryMonsterSchema,
        diagram_models=(BestiaryMonsterSchema,),
        diagram_terminals=(BestiaryActionSchema,),
    ),
    SchemaDocument(
        slug="bestiary-capabilities",
        title="Bestiary capabilities",
        description=(
            "Attacks, saving-throw capabilities, spellcasting, and Multiattack "
            "accepted by stat-block actions."
        ),
        schema_type=BestiaryCapabilitySchema,
    ),
    SchemaDocument(
        slug="creatures",
        title="Encounter creatures",
        description="Creature instances assembled from stat blocks and character data.",
        schema_type=CreatureSchema,
        diagram_models=(CreatureSchema,),
    ),
    SchemaDocument(
        slug="encounters",
        title="Encounters",
        description="Battlefield, teams, controllers, and placed creatures.",
        schema_type=EncounterDefinitionSchema,
        diagram_models=(EncounterDefinitionSchema,),
    ),
    SchemaDocument(
        slug="equipment",
        title="Equipment",
        description="Item and equipment fields currently consumed by the game.",
        schema_type=ItemSchema,
        diagram_models=(ItemSchema,),
    ),
    SchemaDocument(
        slug="classes",
        title="Classes",
        description="Class, subclass, and feature records in an authored class file.",
        schema_type=ClassFileSchema,
        diagram_models=(ClassFileSchema,),
    ),
)


def _json_schema(schema_type: Any) -> dict[str, Any]:
    if isinstance(schema_type, type) and issubclass(schema_type, BaseModel):
        return schema_type.model_json_schema(by_alias=True)
    return TypeAdapter(schema_type).json_schema(by_alias=True)


def _generate_reference(document: SchemaDocument, output: Path) -> None:
    schema_path = output / f"{document.slug}.json"
    schema_path.write_text(
        json.dumps(_json_schema(document.schema_type), indent=2) + "\n",
        encoding="utf-8",
    )
    configuration = GenerationConfiguration(
        minify=True,
        description_is_markdown=True,
        expand_buttons=True,
        template_name="js",
        show_toc=True,
    )
    generate_from_filename(
        schema_path,
        str(output / f"{document.slug}.html"),
        config=configuration,
    )


def _generate_diagram(document: SchemaDocument, output: Path) -> None:
    if not document.diagram_models:
        return
    diagram = erdantic.create(
        *document.diagram_models,
        terminal_models=document.diagram_terminals,
    )
    diagram.draw(
        output / f"{document.slug}.svg",
        graph_attr={"rankdir": "LR"},
    )


def _write_index(
    documents: list[SchemaDocument],
    output: Path,
    *,
    include_diagrams: bool,
) -> None:
    cards = []
    for document in documents:
        diagram_path = output / f"{document.slug}.svg"
        diagram_link = (
            f'<a href="{document.slug}.svg">Relationship diagram</a>'
            if include_diagrams and diagram_path.is_file()
            else ""
        )
        cards.append(
            f"""
            <article>
              <h2>{html.escape(document.title)}</h2>
              <p>{html.escape(document.description)}</p>
              <nav>
                <a href="{document.slug}.html">Field reference</a>
                <a href="{document.slug}.json">Raw JSON Schema</a>
                {diagram_link}
              </nav>
            </article>
            """
        )
    output.joinpath("index.html").write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SRD Arena content schemas</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { max-width: 72rem; margin: 0 auto; padding: 2rem; }
    main { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1rem; }
    article { border: 1px solid currentColor; border-radius: .6rem; padding: 1rem; }
    h1, h2 { line-height: 1.15; }
    h2 { margin-top: 0; }
    nav { display: flex; flex-wrap: wrap; gap: .8rem; }
  </style>
</head>
<body>
  <h1>SRD Arena content schemas</h1>
  <p>Generated directly from the production Pydantic models. Start with a relationship diagram, then use the field reference for exact alternatives and constraints.</p>
  <main>
    {cards}
  </main>
</body>
</html>
""".replace("{cards}", "\n".join(cards)),
        encoding="utf-8",
    )


def generate_content_schema_docs(
    output: Path,
    *,
    selected_slugs: set[str] | None = None,
    include_diagrams: bool = True,
) -> list[SchemaDocument]:
    """Generate selected schema views and return their specifications."""
    documents = [
        document
        for document in SCHEMA_DOCUMENTS
        if selected_slugs is None or document.slug in selected_slugs
    ]
    output.mkdir(parents=True, exist_ok=True)
    for document in documents:
        _generate_reference(document, output)
        if include_diagrams:
            _generate_diagram(document, output)
    _write_index(documents, output, include_diagrams=include_diagrams)
    return documents


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate browsable documentation from content Pydantic models."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[document.slug for document in SCHEMA_DOCUMENTS],
        help="Generate only this view. May be supplied more than once.",
    )
    parser.add_argument(
        "--no-diagrams",
        action="store_true",
        help="Skip SVG relationship diagrams.",
    )
    return parser


def main() -> None:
    """Run the content-schema documentation generator."""
    arguments = _parser().parse_args()
    documents = generate_content_schema_docs(
        arguments.output,
        selected_slugs=set(arguments.only) if arguments.only else None,
        include_diagrams=not arguments.no_diagrams,
    )
    print(f"Generated {len(documents)} schema views in {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
