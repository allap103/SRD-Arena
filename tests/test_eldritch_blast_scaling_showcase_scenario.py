from pathlib import Path

from srd_arena.domain.spells.rules import spell_max_targets
from srd_arena.infrastructure.scenarios import load_scenario_directory

SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "eldritch_blast_scaling_showcase"
)


def test_eldritch_blast_scaling_showcase_loads_all_caster_thresholds() -> None:
    session = load_scenario_directory(str(SCENARIO_DIR)).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    expected_beams = {
        1: 1,
        3: 1,
        5: 2,
        7: 2,
        9: 2,
        11: 3,
        15: 3,
        17: 4,
        20: 4,
    }
    for level, beam_count in expected_beams.items():
        creature_ref = f"caster_level_{level}"
        caster = state.creatures[creature_ref].creature
        assert caster.spellcasting is not None
        assert [spell.name for spell in caster.spellcasting.learned_spells] == [
            "Eldritch Blast"
        ]
        spell = caster.spellcasting.learned_spells[0]
        assert (
            spell_max_targets(
                spell,
                None,
                caster_level=caster.attributes.level,
            )
            == beam_count
        )
        assert creature_ref in state.initiative_order

    target_refs = {f"target_dummy_{index}" for index in range(1, 4)}
    assert target_refs.isdisjoint(state.initiative_order)
    assert all(
        state.creatures[target_ref].creature.get_health() >= 500
        for target_ref in target_refs
    )
