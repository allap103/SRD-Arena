"""Load reusable player-character templates from scenario content."""

from pathlib import Path

from srd_arena.content.common.sources import load_json

from .schema import CreatureSchema

type PlayerCharacterTemplates = dict[str, CreatureSchema]


def load_player_character_templates(
    directory: str | Path,
) -> PlayerCharacterTemplates:
    """Load each authored player-character file as a reusable domain template.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory) / "hero.json"
    ...     _ = path.write_text('{"id": "hero", "name": "Hero"}')
    ...     templates = load_player_character_templates(directory)
    >>> templates["hero"].name
    'Hero'
    """

    player_characters_dir = Path(directory)
    if not player_characters_dir.is_dir():
        return {}
    return {
        schema.id: schema
        for schema in (
            CreatureSchema.model_validate(load_json(path))
            for path in player_characters_dir.glob("*")
        )
    }
