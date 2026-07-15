from pathlib import Path

import pytest

from game.combat.encounter import EncounterState
from game.runtime.scenario import Game
from game.combat.encounter import EncounterAction
from game.rules import RuleGrant, matching_rules, reroll_eligible_indices
from game.runtime.save import load_from_file, save_to_file
from game.systems.roll import reroll_dice, resolve_dice

SAMPLE_GAME_DIR = Path(__file__).parents[1] / "app" / "content" / "scenarios" / "sample_game"


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
    player = Game(SAMPLE_GAME_DIR).create_session().player

    [rule] = [
        rule for rule in player.rule_grants if rule.id == "great_weapon_fighting"
    ]

    assert rule.operation == "reroll_matching_dice"
    assert rule.parameters["values"] == [1, 2]
    assert player.equipment.equipped_items["right_hand"] == "greatsword"


def test_great_weapon_fighting_pauses_damage_and_rerolls_each_die_once(
    monkeypatch,
):
    session = _adjacent_sample_encounter()
    damage_rolls = iter([1, 2, 6, 1])
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr(
        "game.combat.encounter.roll_dice",
        lambda _count, _sides: next(damage_rolls, 1),
    )

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    initial = session.choose(attack_index)

    assert session.encounter_state is not None
    assert session.encounter_state.current_decision().kind == "reroll_dice"
    assert session.encounter_state.enemies[0].actor.get_health() == 7
    assert [action.kind for action in session.encounter_state.available_actions(session.player)] == [
        "reroll_die",
        "reroll_die",
        "accept_roll",
    ]
    pending_event = next(event for event in initial.events if event.type == "attack_pending")
    assert pending_event.data["eligible_die_indices"] == [0, 1]

    first_reroll = session.choose(
        session.get_scene_view().choices.index("Reroll damage die 1 (1)")
    )

    assert session.encounter_state.current_decision().kind == "reroll_dice"
    assert session.encounter_state.enemies[0].actor.get_health() == 7
    reroll_event = next(
        event for event in first_reroll.events if event.type == "damage_rerolled"
    )
    assert reroll_event.data["damage_roll_detail"]["die_rolls"] == [[1, 6], [2]]

    final = session.choose(
        session.get_scene_view().choices.index("Reroll damage die 2 (2)")
    )

    assert session.encounter_state.current_decision().kind == "turn"
    assert session.encounter_state.pending_attack is None
    assert session.encounter_state.enemies[0].actor.get_health() == 0
    resolved = next(event for event in final.events if event.type == "attack_resolved")
    assert resolved.data["damage_roll_detail"]["die_rolls"] == [[1, 6], [2, 1]]
    assert resolved.data["damage_roll_detail"]["dice_total"] == 7


def test_pending_damage_reroll_survives_save_and_load(tmp_path, monkeypatch):
    session = _adjacent_sample_encounter()
    damage_rolls = iter([1, 5])
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr(
        "game.combat.encounter.roll_dice",
        lambda _count, _sides: next(damage_rolls, 1),
    )
    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(attack_index)

    save_path = tmp_path / "pending-reroll.json"
    save_to_file(session, save_path)
    restored = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert restored.encounter_state is not None
    assert restored.encounter_state.current_decision().kind == "reroll_dice"
    assert restored.encounter_state.pending_attack is not None
    assert restored.encounter_state.pending_attack.attack.damage_roll is not None
    assert [
        die.rolls
        for die in restored.encounter_state.pending_attack.attack.damage_roll.dice
    ] == [(1,), (5,)]
    assert "Reroll damage die 1 (1)" in restored.get_scene_view().choices


def test_great_weapon_fighting_can_decline_rerolls(monkeypatch):
    session = _adjacent_sample_encounter()
    damage_rolls = iter([1, 5])
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr(
        "game.combat.encounter.roll_dice",
        lambda _count, _sides: next(damage_rolls, 1),
    )
    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(attack_index)

    result = session.choose(
        session.get_scene_view().choices.index("Use current damage")
    )

    assert session.encounter_state is not None
    assert session.encounter_state.pending_attack is None
    resolved = next(event for event in result.events if event.type == "attack_resolved")
    assert resolved.data["damage_roll_detail"]["die_rolls"] == [[1], [5]]


def test_great_weapon_fighting_does_not_trigger_for_one_handed_weapon(monkeypatch):
    session = _adjacent_sample_encounter()
    session.player.equipment.equipped_items["right_hand"] = "longsword"
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr("game.combat.encounter.roll_dice", lambda _count, _sides: 1)
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


def test_opportunity_attack_reroll_resumes_interrupted_movement(monkeypatch):
    session = _sample_opportunity_attack()
    damage_rolls = iter([1, 2, 6, 5])
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr(
        "game.combat.encounter.roll_dice",
        lambda _count, _sides: next(damage_rolls, 1),
    )

    opportunity = session.choose(
        session.get_scene_view().choices.index("Opportunity attack Goblin")
    )

    assert session.encounter_state is not None
    state = session.encounter_state
    assert [frame.kind for frame in state.decision_stack] == [
        "reaction",
        "reroll_dice",
    ]
    assert state.enemies[0].position.x == 3
    assert state.enemies[0].actor.get_health() == 30
    assert next(event for event in opportunity.events if event.type == "attack_pending").data[
        "reaction"
    ] is True

    session.choose(session.get_scene_view().choices.index("Reroll damage die 1 (1)"))
    final = session.choose(
        session.get_scene_view().choices.index("Reroll damage die 2 (2)")
    )

    assert state.pending_attack is None
    assert state.pending_action is None
    assert state.decision_stack == []
    assert state.enemies[0].actor.get_health() == 15
    assert state.enemies[0].position.x > 3
    resolved = next(event for event in final.events if event.type == "attack_resolved")
    assert resolved.data["reaction"] is True
    assert len(
        [event for event in final.events if event.type == "decision_closed"]
    ) >= 2


def test_nested_opportunity_reroll_survives_save_and_load(tmp_path, monkeypatch):
    session = _sample_opportunity_attack()
    damage_rolls = iter([1, 5])
    monkeypatch.setattr("game.combat.encounter.roll_die", lambda _sides: 15)
    monkeypatch.setattr(
        "game.combat.encounter.roll_dice",
        lambda _count, _sides: next(damage_rolls, 1),
    )
    session.choose(
        session.get_scene_view().choices.index("Opportunity attack Goblin")
    )

    save_path = tmp_path / "nested-reroll.json"
    save_to_file(session, save_path)
    restored = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert restored.encounter_state is not None
    state = restored.encounter_state
    assert [frame.kind for frame in state.decision_stack] == [
        "reaction",
        "reroll_dice",
    ]
    assert state.pending_action is not None
    assert state.pending_attack is not None
    assert state.pending_attack.continuation == "complete_reaction"
    assert state.pending_attack.reaction is True

    monkeypatch.setattr("game.combat.encounter.roll_dice", lambda _count, _sides: 6)
    restored.choose(
        restored.get_scene_view().choices.index("Reroll damage die 1 (1)")
    )

    assert state.pending_attack is None
    assert state.pending_action is None
    assert state.decision_stack == []


def _adjacent_sample_encounter():
    session = Game(SAMPLE_GAME_DIR, start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    return session


def _sample_opportunity_attack():
    session = Game(SAMPLE_GAME_DIR, start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[0].actor.current_health = 30
    state.turn_index = 1

    def scripted_behavior():
        _ = yield None
        while True:
            _ = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    state._behaviors[0] = behavior
    progress = state.advance_until_next_decision(session.player)
    assert progress.paused_for_decision is True
    assert state.current_decision().kind == "reaction"
    session.get_scene_view()
    return session
