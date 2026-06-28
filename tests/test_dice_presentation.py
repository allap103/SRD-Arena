from game.dice_presentation import build_roll_views, without_roll_details
from game.encounter import CombatEvent


def test_build_roll_views_extracts_attack_and_damage():
    event = CombatEvent(
        seq=1,
        type="attack_resolved",
        data={
            "attacker_label": "Fighter",
            "target_label": "Target",
            "hit": True,
            "attack_roll_detail": {
                "die": 17,
                "modifier": 5,
                "total": 22,
                "target_ac": 15,
            },
            "damage_roll_detail": {
                "dice": "2d6",
                "dice_total": 9,
                "modifier": 3,
                "total": 12,
            },
        },
    )

    attack, damage = build_roll_views([event])

    assert attack.label == "Fighter attacks Target"
    assert attack.dice[0].expression == "d20"
    assert attack.dice[0].value == 17
    assert attack.total == 22
    assert attack.target == 15
    assert attack.success is True
    assert damage.label == "Damage"
    assert damage.dice[0].expression == "2d6"
    assert damage.dice[0].value == 9
    assert damage.total == 12


def test_build_roll_views_extracts_feature_healing():
    event = CombatEvent(
        seq=1,
        type="feature_used",
        data={
            "healing_roll_detail": {
                "dice": "1d10",
                "dice_total": 7,
                "modifier": 2,
                "total": 9,
            }
        },
    )

    [healing] = build_roll_views([event])

    assert healing.label == "Healing"
    assert healing.modifier == 2
    assert healing.total == 9


def test_build_roll_views_exposes_individual_rerollable_damage_dice():
    event = CombatEvent(
        seq=1,
        type="attack_pending",
        data={
            "hit": True,
            "roll_id": "action-1:damage",
            "reroll_action_ids": {
                "0": "action-1-reroll-damage-0",
                "1": "action-1-reroll-damage-1",
            },
            "attack_roll_detail": {
                "die": 18,
                "modifier": 5,
                "total": 23,
                "target_ac": 15,
            },
            "damage_roll_detail": {
                "dice": "2d6",
                "dice_values": [1, 2],
                "die_rolls": [[1], [2]],
                "dice_total": 3,
                "modifier": 4,
                "total": 7,
            },
        },
    )

    _, damage = build_roll_views([event])

    assert damage.roll_id == "action-1:damage"
    assert [die.expression for die in damage.dice] == ["d6", "d6"]
    assert [die.value for die in damage.dice] == [1, 2]
    assert [die.action_id for die in damage.dice] == [
        "action-1-reroll-damage-0",
        "action-1-reroll-damage-1",
    ]


def test_without_roll_details_keeps_outcomes_and_removes_formula_messages():
    messages = [
        ("system", "Traveler attacks Goblin. Roll d20=17 + STR mod 3 = 20."),
        ("system", "Damage to Goblin: 1d8=6 + STR mod 3 = 9."),
        ("system", "Traveler hits Goblin for 9 damage."),
        ("system", "Healing: 1d10=7 + level 2 = 9; applied 9."),
        ("system", "Traveler uses Second Wind."),
    ]

    assert without_roll_details(messages) == [
        ("system", "Traveler hits Goblin for 9 damage."),
        ("system", "Traveler uses Second Wind."),
    ]
