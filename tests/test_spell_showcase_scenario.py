from pathlib import Path

from srd_arena.content.scenarios import load_scenario_directory
from srd_arena.engine.session import Session

SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "spell_damage_showcase"
)


def test_spell_damage_showcase_loads_wave_1a_demo_spellcaster() -> None:
    session = Session(load_scenario_directory(str(SCENARIO_DIR)))
    session.read()

    assert session.encounter_state is not None
    adept = session.encounter_state.creatures["spectrum_adept"].creature
    assert adept.spellcasting is not None
    assert {spell.name for spell in adept.spellcasting.learned_spells} == {
        "Acid Splash",
        "Blight",
        "Burning Hands",
        "Circle of Death",
        "Cone of Cold",
        "Fire Bolt",
        "Fireball",
        "Flame Strike",
        "Inflict Wounds",
        "Lightning Bolt",
        "Poison Spray",
        "Sacred Flame",
        "Shatter",
    }
    assert all(
        spell.definition is not None for spell in adept.spellcasting.learned_spells
    )
    assert adept.spellcasting.spell_slots_remaining == {
        1: 4,
        2: 3,
        3: 3,
        4: 3,
        5: 2,
        6: 1,
    }
    assert adept.attributes.level == 13
    assert (
        session.encounter_state.creatures[
            "plant_target"
        ].creature.statistics.creature_type
        == "plant"
    )
    assert (
        session.encounter_state.creatures[
            "construct_target"
        ].creature.statistics.creature_type
        == "construct"
    )
