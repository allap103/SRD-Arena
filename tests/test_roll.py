from collections.abc import Iterator

import pytest

from game.systems.roll import resolve_check, resolve_d20, resolve_dice


def _roller(results: list[int]) -> tuple[Iterator[int], object]:
    values = iter(results)
    return values, lambda _sides: next(values)


@pytest.mark.parametrize(
    ("mode", "expected_selected", "expected_total"),
    [
        ("normal", 7, 10),
        ("advantage", 16, 19),
        ("disadvantage", 7, 10),
    ],
)
def test_resolve_d20_selects_die_for_mode(mode, expected_selected, expected_total):
    results = [7] if mode == "normal" else [7, 16]
    _, roller = _roller(results)

    result = resolve_d20(modifier=3, mode=mode, roller=roller)

    assert result.selected == expected_selected
    assert result.total == expected_total


@pytest.mark.parametrize(
    ("roll_value", "target", "expected_success"),
    [(12, 15, False), (13, 15, True)],
)
def test_resolve_check_compares_roll_total(roll_value, target, expected_success):
    roll = resolve_d20(modifier=2, roller=lambda _sides: roll_value)

    result = resolve_check(roll, target)

    assert result.roll is roll
    assert result.target == target
    assert result.success is expected_success


def test_resolve_dice_records_replaced_roll_and_uses_new_result():
    _, roller = _roller([1, 4, 2, 1, 1, 6])

    result = resolve_dice(
        4,
        6,
        modifier=2,
        reroll_values={1},
        max_rerolls_per_die=1,
        roller=roller,
    )

    assert [die.rolls for die in result.dice] == [(1, 4), (2,), (1, 1), (6,)]
    assert result.subtotal == 13
    assert result.total == 15


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"num_dice": 0, "sides": 6}, "num_dice"),
        ({"num_dice": 1, "sides": 1}, "sides"),
        (
            {
                "num_dice": 1,
                "sides": 6,
                "reroll_values": {7},
                "max_rerolls_per_die": 1,
            },
            "reroll_values",
        ),
    ],
)
def test_resolve_dice_rejects_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        resolve_dice(**kwargs)
