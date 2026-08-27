from pathlib import Path

from srd_arena.domain.creatures.feature_rules import (
    CapabilityActionResult,
    resolve_feature_action,
)
from srd_arena.infrastructure.scenarios import load_scenario_directory

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def test_second_wind_returns_healing_effect_result() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.read()
    assert session.encounter_state is not None
    creature = session.encounter_state.creatures["player"].creature
    creature.current_health = 10

    result = resolve_feature_action(creature, "second_wind", lambda num_dice, sides: 5)

    assert isinstance(result, CapabilityActionResult)
    assert result.capability_id == "second_wind"
    assert result.capability_name == "Second Wind"
    assert result.resource_updates == {"second_wind": 1}
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.kind == "healing"
    assert effect.target_ref == "player"
    assert effect.data["amount"] == 7
    assert effect.data["target_label"] == "Traveler"
    assert effect.data["roll"] == {
        "dice": "1d10",
        "dice_total": 5,
        "modifier": 2,
        "total": 7,
        "applied_healing": 7,
    }


def test_action_surge_returns_extra_action_result() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.read()
    assert session.encounter_state is not None
    creature = session.encounter_state.creatures["player"].creature

    result = resolve_feature_action(creature, "action_surge", lambda num_dice, sides: 0)

    assert isinstance(result, CapabilityActionResult)
    assert result.capability_id == "action_surge"
    assert result.capability_name == "Action Surge"
    assert result.resource_updates == {"action_surge": 0}
    assert result.effects == []
    assert result.details["grant_actions"] == 1
