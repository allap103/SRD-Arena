from pathlib import Path

from .schema import CreatureSchema
from srd_arena.content.common.sources import load_json

type PlayerCharacterTemplates = dict[str, CreatureSchema]


def load_player_character_templates(
    directory: str | Path,
) -> PlayerCharacterTemplates:
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
