from pathlib import Path

import pytest
from pydantic import ValidationError

from srd_arena.content.encounters import load_encounter_directory

EXAMPLE_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "invalid_encounter_showcase"
)


def test_invalid_encounter_example_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            r"Encounter creature starting positions must lie within the grid: "
            r"outside_goblin at \(5, 2\)"
        ),
    ):
        load_encounter_directory(EXAMPLE_DIR)
