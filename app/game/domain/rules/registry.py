from collections.abc import Iterable, Mapping

from .dice import DicePoolResult
from .types import RuleGrant


def matching_rules(
    rules: Iterable[RuleGrant],
    trigger: str,
    context: Mapping[str, object],
) -> list[RuleGrant]:
    return [
        rule
        for rule in rules
        if rule.trigger == trigger and _conditions_match(rule.conditions, context)
    ]


def reroll_eligible_indices(
    rule: RuleGrant,
    pool: DicePoolResult,
) -> tuple[int, ...]:
    if rule.operation != "reroll_matching_dice":
        return ()
    values = rule.parameters.get("values", [])
    if not isinstance(values, list):
        return ()
    qualifying_values = {value for value in values if isinstance(value, int)}
    maximum_per_die = rule.parameters.get("maximum_per_die", 1)
    if not isinstance(maximum_per_die, int):
        maximum_per_die = 1
    rerolls_by_index: dict[int, int] = {}
    for replacement in pool.replacements:
        rerolls_by_index[replacement.die_index] = (
            rerolls_by_index.get(replacement.die_index, 0) + 1
        )
    return tuple(
        index
        for index, die in enumerate(pool.dice)
        if die.result in qualifying_values
        and rerolls_by_index.get(index, 0) < maximum_per_die
    )


def _conditions_match(
    conditions: Mapping[str, object],
    context: Mapping[str, object],
) -> bool:
    for key, expected in conditions.items():
        if key.endswith("_any"):
            actual = context.get(key.removesuffix("_any"))
            if not _has_overlap(actual, expected):
                return False
            continue
        if context.get(key) != expected:
            return False
    return True


def _has_overlap(actual: object, expected: object) -> bool:
    if not isinstance(actual, (list, set, tuple)):
        return False
    if not isinstance(expected, (list, set, tuple)):
        return False
    return bool(set(actual).intersection(expected))
