from pathlib import Path

import pytest

from srd_arena.domain.combat.encounter import EncounterState
from srd_arena.runtime.scenario import Scenario
from srd_arena.domain.rules import RuleGrant, matching_rules, reroll_eligible_indices
from srd_arena.domain.rules.dice import reroll_dice, resolve_dice

SAMPLE_SCENARIO_DIR = Path(__file__).parents[1] / "content" / "scenarios" / "sample_game"


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self, player):
        self.initiative_entries = []
        self.initiative_order = [
            "player",
            *(f"enemy:{index}" for index, _enemy in enumerate(self.enemies)),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def test_rule_matching_uses_generic_context_conditions():
    rule = RuleGrant(
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

    assert matching_rules(
        [rule],
        "weapon_damage_rolled",
        {
            "attack_type": "melee",
            "weapon_properties": ["heavy", "two-handed"],
        },
    ) == [rule]
    assert matching_rules(
        [rule],
        "weapon_damage_rolled",
        {
            "attack_type": "ranged",
            "weapon_properties": ["heavy", "two-handed"],
        },
    ) == []


def test_reroll_matching_dice_enforces_maximum_per_die():
    rule = RuleGrant(
        id="test",
        source_type="test",
        source_id="test",
        trigger="weapon_damage_rolled",
        operation="reroll_matching_dice",
        parameters={"values": [1, 2], "maximum_per_die": 1},
    )
    rolls = iter([1, 2])
    pool = resolve_dice(2, 6, roller=lambda _sides: next(rolls))

    assert reroll_eligible_indices(rule, pool) == (0, 1)

    rerolled = reroll_dice(pool, [0], roller=lambda _sides: 1)

    assert rerolled.dice[0].rolls == (1, 1)
    assert reroll_eligible_indices(rule, rerolled) == (1,)


def test_sample_fighter_loads_great_weapon_fighting_rule():
    player = Scenario(SAMPLE_SCENARIO_DIR).create_session().player

    [rule] = [
        rule for rule in player.rule_grants if rule.id == "great_weapon_fighting"
    ]

    assert rule.operation == "reroll_matching_dice"
    assert rule.parameters["values"] == [1, 2]
    assert player.equipment.equipped_items["right_hand"] == "greatsword"


def test_great_weapon_fighting_does_not_trigger_for_one_handed_weapon(monkeypatch):
    session = _adjacent_sample_encounter()
    session.player.equipment.equipped_items["right_hand"] = "longsword"
    monkeypatch.setattr("srd_arena.domain.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr("srd_arena.domain.combat.encounter.roll_dice", lambda _count, _sides: 1)
    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )

    result = session.choose(attack_index)

    assert session.encounter_state is not None
    assert session.encounter_state.pending_attack is None
    assert any(event.type == "attack_resolved" for event in result.events)
    assert not any(event.type == "attack_pending" for event in result.events)


def _adjacent_sample_encounter():
    session = Scenario(SAMPLE_SCENARIO_DIR, start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    return session
