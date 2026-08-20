from pathlib import Path

from srd_arena.runtime.scenario import Scenario


SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_spell_modifier_showcase_loads_new_modifier_spells() -> None:
    scenario = Scenario(SCENARIOS_ROOT / "spell_modifier_showcase")
    session = scenario.create_session()
    session.get_scene_view()

    caster = scenario.get_creature("modifier_archmage")
    assert caster.spellcasting is not None
    assert {spell.name for spell in caster.spellcasting.learned_spells} == {
        "Bane",
        "Bless",
        "Blur",
        "Darkvision",
        "Foresight",
        "Heroism",
        "Longstrider",
        "Protection from Energy",
        "Protection from Poison",
        "Resistance",
        "Shield of Faith",
        "Stoneskin",
        "True Seeing",
    }
    assert session.encounter_state is not None
    assert {
        team.controller for team in session.encounter_state.definition.teams
    } == {"external"}


def test_spell_effect_lifecycle_showcase_loads_recent_spell_lifecycles() -> None:
    scenario = Scenario(SCENARIOS_ROOT / "spell_effect_lifecycle_showcase")
    session = scenario.create_session()
    session.get_scene_view()

    caster = scenario.get_creature("lifecycle_archmage")
    assert caster.spellcasting is not None
    assert {spell.name for spell in caster.spellcasting.learned_spells} == {
        "Enhance Ability",
        "Faerie Fire",
        "Phantasmal Killer",
        "Ray of Frost",
    }
    assert scenario.get_creature("nightmare_subject").get_max_health() == 168
    assert session.encounter_state is not None
    assert {
        team.controller for team in session.encounter_state.definition.teams
    } == {"external"}


def test_bundled_scenario_directories_are_all_showcases() -> None:
    assert all(
        path.name.endswith("_showcase")
        for path in SCENARIOS_ROOT.iterdir()
        if path.is_dir()
    )
