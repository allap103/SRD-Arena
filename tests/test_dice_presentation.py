from srd_arena.engine.commands import GameEvent
from srd_arena.frontends.gui.presentation.dice import (
    build_roll_views,
    without_roll_details,
)


def test_build_roll_views_extracts_attack_and_damage() -> None:
    event = GameEvent(
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


def test_build_roll_views_displays_additional_typed_attack_damage() -> None:
    event = GameEvent(
        seq=1,
        type="attack_resolved",
        data={
            "attacker_label": "White Dragon",
            "target_label": "Target",
            "hit": True,
            "attack_roll_detail": {
                "die": 17,
                "modifier": 11,
                "total": 28,
                "target_ac": 15,
            },
            "damage_roll_detail": {
                "dice": "2d6",
                "dice_total": 7,
                "modifier": 6,
                "total": 13,
                "damage_type": "slashing",
                "additional_damage": (
                    {
                        "dice": "1d8",
                        "dice_values": (5,),
                        "die_rolls": ((5,),),
                        "dice_total": 5,
                        "modifier": 0,
                        "total": 5,
                        "damage_type": "cold",
                    },
                ),
            },
        },
    )

    attack, slashing, cold = build_roll_views([event])

    assert attack.label == "White Dragon attacks Target"
    assert slashing.label == "Slashing damage"
    assert slashing.total == 13
    assert cold.label == "Cold damage"
    assert cold.dice[0].expression == "d8"
    assert cold.total == 5


def test_build_roll_views_shows_both_d20s_for_advantage_or_disadvantage() -> None:
    event = GameEvent(
        seq=1,
        type="attack_resolved",
        data={
            "attacker_label": "Goblin",
            "target_label": "Traveler",
            "hit": False,
            "attack_roll_detail": {
                "die": 5,
                "dice": (17, 5),
                "selected_index": 1,
                "mode": "disadvantage",
                "modifier": 4,
                "total": 9,
                "target_ac": 16,
            },
        },
    )

    [attack] = build_roll_views([event])

    assert [die.value for die in attack.dice] == [17, 5]
    assert [die.selected for die in attack.dice] == [False, True]


def test_build_roll_views_shows_full_attack_pool_for_three_d20s() -> None:
    event = GameEvent(
        seq=1,
        type="attack_resolved",
        data={
            "attacker_label": "Elf",
            "target_label": "Goblin",
            "hit": True,
            "attack_roll_detail": {
                "die": 19,
                "dice": (12, 19, 7),
                "selected_index": 1,
                "mode": "advantage",
                "modifier": 7,
                "total": 26,
                "target_ac": 15,
            },
        },
    )

    [attack] = build_roll_views([event])

    assert [die.value for die in attack.dice] == [12, 19, 7]
    assert [die.selected for die in attack.dice] == [False, True, False]


def test_build_roll_views_extracts_feature_healing() -> None:
    event = GameEvent(
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


def test_build_roll_views_extracts_spell_save_dice() -> None:
    event = GameEvent(
        seq=1,
        type="spell_cast",
        data={
            "spell_name": "Color Spray",
            "save_details": (
                {
                    "target_label": "Goblin",
                    "ability": "constitution",
                    "die": 4,
                    "dice": (15, 4),
                    "selected_index": 1,
                    "modifier": 2,
                    "total": 6,
                    "target_dc": 12,
                    "success": False,
                },
            ),
        },
    )

    [save] = build_roll_views([event])

    assert save.label == "Goblin Constitution save vs Color Spray"
    assert [die.value for die in save.dice] == [15, 4]
    assert [die.selected for die in save.dice] == [False, True]
    assert save.modifier == 2
    assert save.total == 6
    assert save.target == 12
    assert save.success is False


def test_build_roll_views_extracts_spell_damage_dice() -> None:
    event = GameEvent(
        seq=1,
        type="spell_cast",
        data={
            "spell_name": "Burning Hands",
            "damage_roll_details": (
                {
                    "target_label": "Goblin",
                    "dice": "3d6",
                    "dice_values": (2, 5, 6),
                    "die_rolls": ((2,), (5,), (6,)),
                    "dice_total": 13,
                    "modifier": 0,
                    "total": 13,
                },
            ),
        },
    )

    [damage] = build_roll_views([event])

    assert damage.label == "Goblin takes damage from Burning Hands"
    assert [die.expression for die in damage.dice] == ["d6", "d6", "d6"]
    assert [die.value for die in damage.dice] == [2, 5, 6]
    assert damage.modifier == 0
    assert damage.total == 13


def test_spell_damage_view_explains_save_and_defense_reductions() -> None:
    event = GameEvent(
        seq=1,
        type="spell_cast",
        data={
            "spell_name": "Phantasmal Killer",
            "damage_roll_details": (
                {
                    "target_label": "Veteran",
                    "dice": "4d10",
                    "dice_values": (5, 5, 5, 5),
                    "die_rolls": ((5,), (5,), (5,), (5,)),
                    "dice_total": 20,
                    "modifier": 0,
                    "total": 20,
                    "saved": True,
                    "final_damage": 10,
                    "applied_damage": 5,
                },
            ),
        },
    )

    [damage] = build_roll_views([event])

    assert damage.total == 20
    assert damage.resolution_notes == (
        "Successful save: 10 damage",
        "Applied to target: 5 damage",
    )


def test_build_roll_views_extracts_ongoing_spell_save_and_damage() -> None:
    event = GameEvent(
        seq=1,
        type="ongoing_effect_resolved",
        data={
            "spell_name": "Phantasmal Killer",
            "save_detail": {
                "target_label": "Veteran",
                "ability": "wisdom",
                "die": 7,
                "dice": (7,),
                "selected_index": 0,
                "modifier": 1,
                "total": 8,
                "target_dc": 16,
                "success": False,
            },
            "damage_roll_details": (
                {
                    "target_label": "Veteran",
                    "dice": "4d10",
                    "dice_values": (2, 4, 6, 8),
                    "die_rolls": ((2,), (4,), (6,), (8,)),
                    "dice_total": 20,
                    "modifier": 0,
                    "total": 20,
                },
            ),
        },
    )

    save, damage = build_roll_views([event])

    assert save.label == "Veteran Wisdom save vs Phantasmal Killer"
    assert save.total == 8
    assert save.success is False
    assert damage.label == "Veteran takes damage from Phantasmal Killer"
    assert [die.value for die in damage.dice] == [2, 4, 6, 8]
    assert damage.total == 20


def test_build_roll_views_extracts_each_invocation_start_check() -> None:
    event = GameEvent(
        seq=1,
        type="invocation_start_checked",
        data={
            "kind": "cast_spell",
            "checks": (
                {
                    "source": {
                        "definition_id": "slow",
                        "label": "Tempo Archmage",
                    },
                    "numerator": 1,
                    "denominator": 4,
                    "roll": 1,
                    "failed": True,
                },
                {
                    "source": {
                        "definition_id": "arcane_interference",
                        "label": "Interference Adept",
                    },
                    "numerator": 2,
                    "denominator": 6,
                    "roll": 5,
                    "failed": False,
                },
            ),
        },
    )

    slow, interference = build_roll_views([event])

    assert slow.label == "Slow spellcasting check"
    assert slow.dice[0].expression == "d4"
    assert slow.dice[0].value == 1
    assert slow.modifier == 0
    assert slow.total == 1
    assert slow.target == 2
    assert slow.success is False
    assert interference.label == "Arcane Interference spellcasting check"
    assert interference.dice[0].expression == "d6"
    assert interference.dice[0].value == 5
    assert interference.target == 3
    assert interference.success is True


def test_build_roll_views_exposes_individual_rerollable_damage_dice() -> None:
    event = GameEvent(
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
                "dice_values": (1, 2),
                "die_rolls": ((1,), (2,)),
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


def test_without_roll_details_keeps_outcomes_and_removes_formula_messages() -> None:
    messages = [
        ("system", "Traveler attacks Goblin. Roll d20=17 + STR mod 3 = 20."),
        ("system", "Damage to Goblin: 1d8=6 + STR mod 3 = 9."),
        ("system", "Goblin makes a Constitution save: d20=4 + 2 = 6 vs DC 12."),
        ("system", "Traveler hits Goblin for 9 damage."),
        ("system", "Traveler misses Goblin."),
        ("system", "Healing: 1d10=7 + level 2 = 9; applied 9."),
        ("system", "Traveler uses Second Wind."),
    ]

    assert without_roll_details(messages) == [
        ("system", "Traveler hits Goblin for 9 damage."),
        ("system", "Traveler uses Second Wind."),
    ]
