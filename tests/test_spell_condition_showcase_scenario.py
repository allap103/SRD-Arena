from pathlib import Path

from srd_arena.domain.effects.conditions import Condition
from srd_arena.runtime.scenario import Scenario


SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "spell_condition_showcase"
)


def test_spell_condition_showcase_loads_wave_1b_capability() -> None:
    session = Scenario(str(SCENARIO_DIR)).create_session()
    session.get_scene_view()

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
        spell.capability is not None
        for spell in savant.spellcasting.learned_spells
    )
    assert state._creature_controller("lifecycle_savant") == "external"
    assert state._creature_controller("sleep_target") == "external"
    assert (
        state.creatures["beast_target"].creature.statistics.creature_type
        == "beast"
    )
    assert Condition.EXHAUSTION in (
        state.creatures["sleep_immune_target"]
        .creature.statistics.condition_immunities
    )
