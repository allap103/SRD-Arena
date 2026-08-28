from pathlib import Path

from srd_arena.infrastructure.scenarios import load_scenario_directory

SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_spell_modifier_showcase_loads_new_modifier_spells() -> None:
    scenario = load_scenario_directory(SCENARIOS_ROOT / "spell_modifier_showcase")
    session = scenario.create_session()
    session.read()

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
    assert {team.controller for team in session.encounter_state.definition.teams} == {
        "external"
    }


def test_spell_effect_lifecycle_showcase_loads_recent_spell_lifecycles() -> None:
    scenario = load_scenario_directory(
        SCENARIOS_ROOT / "spell_effect_lifecycle_showcase"
    )
    session = scenario.create_session()
    session.read()

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
    assert {team.controller for team in session.encounter_state.definition.teams} == {
        "external"
    }


def test_slow_showcase_exposes_six_of_seven_rules_subjects() -> None:
    scenario = load_scenario_directory(SCENARIOS_ROOT / "slow_showcase")
    session = scenario.create_session()
    session.read()

    caster = scenario.get_creature("tempo_archmage")
    assert caster.spellcasting is not None
    assert [spell.name for spell in caster.spellcasting.learned_spells] == ["Slow"]
    fighter = scenario.get_creature("extra_attack_fighter")
    assert fighter.combat_profile.attacks_per_attack_action == 2
    somatic_caster = scenario.get_creature("somatic_caster")
    assert somatic_caster.spellcasting is not None
    assert {spell.name for spell in somatic_caster.spellcasting.learned_spells} == {
        "Cure Wounds",
        "Healing Word",
    }
    assert session.encounter_state is not None
    state = session.encounter_state
    assert len(state.definition.teams[1].members) == 7
    assert {team.controller for team in state.definition.teams} == {"external"}


def test_bundled_scenario_directories_are_all_showcases() -> None:
    assert all(
        path.name.endswith("_showcase")
        for path in SCENARIOS_ROOT.iterdir()
        if path.is_dir()
    )
