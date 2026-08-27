from collections.abc import Iterator
from typing import TypedDict

import pytest

from srd_arena.domain.rolls.dice import (
    D20RollMode,
    DieRoller,
    extend_d20_pool,
    reroll_dice,
    reroll_dice_pool,
    roll_d20_pool,
    resolve_check,
    resolve_d20,
    resolve_dice,
    resolve_roll_attempts,
    select_d20,
)


class ResolveDiceKwargs(TypedDict, total=False):
    num_dice: int
    sides: int
    reroll_values: set[int]
    max_rerolls_per_die: int


def _roller(results: list[int]) -> tuple[Iterator[int], DieRoller]:
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
def test_resolve_d20_selects_die_for_mode(
    mode: D20RollMode,
    expected_selected: int,
    expected_total: int,
) -> None:
    results = [7] if mode == "normal" else [7, 16]
    _, roller = _roller(results)

    result = resolve_d20(modifier=3, mode=mode, roller=roller)

    assert result.selected == expected_selected
    assert result.total == expected_total


def test_extended_d20_pool_can_select_highest_of_three() -> None:
    _, roller = _roller([7, 16, 19])
    pool = roll_d20_pool(2, roller=roller)
    extended_pool = extend_d20_pool(pool, roller=roller)

    result = select_d20(
        extended_pool,
        selected_index=2,
        modifier=3,
        mode="advantage",
    )

    assert pool.dice == (7, 16)
    assert extended_pool.dice == (7, 16, 19)
    assert result.selected == 19
    assert result.total == 22


def test_extended_d20_pool_leaves_selection_to_caller() -> None:
    _, roller = _roller([18, 4])
    pool = roll_d20_pool(roller=roller)
    extended_pool = extend_d20_pool(pool, roller=roller)

    original = select_d20(extended_pool, selected_index=0)
    added = select_d20(extended_pool, selected_index=1)

    assert original.selected == 18
    assert added.selected == 4


@pytest.mark.parametrize(
    ("roll_value", "target", "expected_success"),
    [(12, 15, False), (13, 15, True)],
)
def test_resolve_check_compares_roll_total(
    roll_value: int,
    target: int,
    expected_success: bool,
) -> None:
    roll = resolve_d20(modifier=2, roller=lambda _sides: roll_value)

    result = resolve_check(roll, target)

    assert result.roll is roll
    assert result.target == target
    assert result.success is expected_success


def test_resolve_dice_records_replaced_roll_and_uses_new_result() -> None:
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
    assert [
        (replacement.die_index, replacement.previous, replacement.replacement)
        for replacement in result.replacements
    ] == [(0, 1, 4), (2, 1, 1)]
    assert result.subtotal == 13
    assert result.total == 15


def test_reroll_dice_replaces_only_selected_dice() -> None:
    _, initial_roller = _roller([2, 5, 1, 6])
    pool = resolve_dice(4, 6, roller=initial_roller)
    _, replacement_roller = _roller([4, 3])

    result = reroll_dice(pool, [0, 2], roller=replacement_roller)

    assert [die.result for die in result.dice] == [4, 5, 3, 6]
    assert [die.rolls for die in result.dice] == [(2, 4), (5,), (1, 3), (6,)]
    assert result.subtotal == 18


def test_reroll_dice_pool_creates_independent_attempt() -> None:
    _, initial_roller = _roller([2, 5])
    original = resolve_dice(2, 6, modifier=1, roller=initial_roller)
    _, replacement_roller = _roller([6, 4])

    replacement = reroll_dice_pool(original, roller=replacement_roller)

    assert [die.result for die in original.dice] == [2, 5]
    assert [die.result for die in replacement.dice] == [6, 4]
    assert replacement.modifier == 1
    assert replacement.total == 11
    assert replacement.replacements == ()


def test_resolve_roll_attempts_records_selected_complete_roll() -> None:
    _, roller = _roller([2, 5, 6, 4])
    original = resolve_dice(2, 6, roller=roller)
    replacement = reroll_dice_pool(original, roller=roller)

    resolution = resolve_roll_attempts(
        [original, replacement],
        selected_attempt=1,
        reason="choose_better_pool",
    )

    assert resolution.attempts == (original, replacement)
    assert resolution.selected is replacement
    assert resolution.reason == "choose_better_pool"


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
def test_resolve_dice_rejects_invalid_configuration(
    kwargs: ResolveDiceKwargs,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_dice(**kwargs)
