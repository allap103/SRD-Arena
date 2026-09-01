from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.engine.session import Session

ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "spell_damage_showcase"
)


def test_spell_damage_showcase_loads_wave_1a_demo_spellcaster() -> None:
    encounter = load_encounter_directory(str(ENCOUNTER_DIR))
    session = Session(encounter)
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
    targets = [
        participant
        for participant in encounter.participants
        if participant.creature_id != "spectrum_adept"
    ]
    target_team = next(team for team in encounter.teams if team.id == "targets")
    assert target_team.controller == "scripted"
    assert all(participant.controller is None for participant in targets)
    assert all(
        participant.behavior is not None and participant.behavior.type == "wait"
        for participant in targets
    )
