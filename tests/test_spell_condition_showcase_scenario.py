from pathlib import Path

from srd_arena.content.scenarios import load_scenario_directory
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters.participants import creature_controller
from srd_arena.engine.session import Session

SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "spell_condition_showcase"
)


def test_spell_condition_showcase_loads_wave_1b_capability() -> None:
    session = Session(load_scenario_directory(str(SCENARIO_DIR)))
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    savant = state.creatures["lifecycle_savant"].creature
    assert savant.spellcasting is not None
    assert {spell.name for spell in savant.spellcasting.learned_spells} == {
        "Animal Friendship",
        "Blindness/Deafness",
        "Charm Monster",
        "Charm Person",
        "Color Spray",
        "Greater Invisibility",
        "Hideous Laughter",
        "Hold Monster",
        "Hold Person",
        "Invisibility",
        "Sleep",
    }
    assert all(
        spell.definition is not None for spell in savant.spellcasting.learned_spells
    )
    assert creature_controller(state, "lifecycle_savant") == "external"
    assert creature_controller(state, "sleep_target") == "external"
    assert state.creatures["beast_target"].creature.statistics.creature_type == "beast"
    assert Condition.EXHAUSTION in (
        state.creatures["sleep_immune_target"].creature.statistics.condition_immunities
    )
