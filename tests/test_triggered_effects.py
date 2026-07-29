from pathlib import Path

import pytest

from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.runtime.scenario import Scenario
from srd_arena.domain.effects import (
    TriggeredEffect,
    matching_effects,
    reroll_eligible_indices,
)
from srd_arena.domain.rolls.dice import reroll_dice, resolve_dice

TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self):
        self.initiative_entries = []
        self.initiative_order = [
            self.primary_creature_ref,
            *(
                creature_ref
                for creature_ref in self.creatures
                if creature_ref != self.primary_creature_ref
            ),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def test_triggered_effect_matching_uses_generic_context_conditions():
    effect = TriggeredEffect(
        id="test",
        source_type="test",
        source_id="test",
        trigger="weapon_damage_rolled",
        operation="reroll_matching_dice",
        conditions={
            "attack_type": "melee",
            "weapon_properties_any": ["two-handed", "versatile"],
        },
    )

    assert matching_effects(
        [effect],
        "weapon_damage_rolled",
        {
            "attack_type": "melee",
            "weapon_properties": ["heavy", "two-handed"],
        },
    ) == [effect]
    assert matching_effects(
        [effect],
        "weapon_damage_rolled",
        {
            "attack_type": "ranged",
            "weapon_properties": ["heavy", "two-handed"],
        },
    ) == []


def test_reroll_matching_dice_enforces_maximum_per_die():
    effect = TriggeredEffect(
        id="test",
        source_type="test",
        source_id="test",
        trigger="weapon_damage_rolled",
        operation="reroll_matching_dice",
        parameters={"values": [1, 2], "maximum_per_die": 1},
    )
    rolls = iter([1, 2])
    pool = resolve_dice(2, 6, roller=lambda _sides: next(rolls))

    assert reroll_eligible_indices(effect, pool) == (0, 1)

    rerolled = reroll_dice(pool, [0], roller=lambda _sides: 1)

    assert rerolled.dice[0].rolls == (1, 1)
    assert reroll_eligible_indices(effect, rerolled) == (1,)


def test_tactical_fighter_loads_great_weapon_fighting_effect():
    player = Scenario(
        TACTICAL_SCENARIO_DIR
    ).create_session().primary_creature

    [effect] = [
        effect
        for effect in player.triggered_effects
        if effect.id == "great_weapon_fighting"
    ]

    assert effect.operation == "reroll_matching_dice"
    assert effect.parameters["values"] == [1, 2]
    assert player.equipment.equipped_items["right_hand"] == "greatsword"


def test_great_weapon_fighting_does_not_trigger_for_one_handed_weapon(monkeypatch):
    session = _adjacent_tactical_encounter()
    session.primary_creature.equipment.equipped_items["right_hand"] = "longsword"
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda _count, _sides: 1)
    attack_index = next(
        action.index
        for action in session.get_scene_view().action_details
        if action.kind == "attack" and action.value == "goblin_1"
    )

    result = session.choose(attack_index)

    assert session.encounter_state is not None
    assert session.encounter_state.pending_attack is None
    assert any(event.type == "attack_resolved" for event in result.events)
    assert not any(event.type == "attack_pending" for event in result.events)


def _adjacent_tactical_encounter():
    session = Scenario(TACTICAL_SCENARIO_DIR, start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.primary_position.x = 4
    session.encounter_state.primary_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    return session
