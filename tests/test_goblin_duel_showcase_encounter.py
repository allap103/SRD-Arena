from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.engine.session import Session

ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "goblin_duel_showcase"
)


def test_goblin_duel_is_fully_scripted() -> None:
    encounter = load_encounter_directory(ENCOUNTER_DIR)
    session = Session(encounter)
    session.read()

    assert encounter.display_name == "3. Goblin Duel Demo"
    assert len(encounter.teams) == 2
    assert len(encounter.participants) == 2
    assert {team.controller for team in encounter.teams} == {"scripted"}
    assert all(
        participant.behavior is not None and participant.behavior.type == "chase"
        for participant in encounter.participants
    )
    assert session.encounter_state is not None
    assert session.encounter_state.requires_automatic_advance() is True
