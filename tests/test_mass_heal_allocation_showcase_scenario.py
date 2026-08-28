from pathlib import Path

from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.infrastructure.scenarios import load_scenario_directory

SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "mass_heal_allocation_showcase"
)
_ORCHESTRATOR = EncounterOrchestrator()


def test_mass_heal_showcase_starts_with_more_than_700_missing_hit_points() -> None:
    session = load_scenario_directory(
        str(SCENARIO_DIR), start_scene="mass_heal_allocation_showcase"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    healer = state.creatures["healer"].creature
    assert healer.spellcasting is not None
    assert [spell.name for spell in healer.spellcasting.learned_spells] == ["Mass Heal"]
    missing_hit_points = sum(
        combatant.creature.get_max_health() - combatant.creature.get_health()
        for ref, combatant in state.creatures.items()
        if state._creature_team_id(ref) == "wounded_party"
    )
    assert missing_hit_points == 900
    assert state.creatures["observer"].is_alive

    cast = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value).startswith("mass_heal:")
    )
    result = _ORCHESTRATOR.submit(state, cast)

    assert result.paused_for_decision
    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.resource_pool_total == 700
    assert state.pending_spell_cast.resource_allocation_limits == {
        "healer": 200,
        "guardian": 450,
        "champion": 200,
        "scout": 50,
    }
