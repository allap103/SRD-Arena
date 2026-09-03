"""Match conditional mechanics against events produced during resolution."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from srd_arena.domain.rolls.dice import DicePoolResult


@dataclass(frozen=True)
class TriggeredEffect:
    """Describe an operation offered when an event matches its conditions.

    Triggered effects are reusable rule declarations. Runtime orchestration
    supplies the event context and performs the named operation.
    """

    id: str
    source_type: str
    source_id: str
    trigger: str
    operation: str
    conditions: dict[str, object] = field(default_factory=dict)
    parameters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TriggeredNumericContribution:
    """Retain the source and value of one resolved numeric trigger."""

    effect_id: str
    source_id: str
    value: int


def matching_effects(
    effects: Iterable[TriggeredEffect],
    trigger: str,
    context: Mapping[str, object],
) -> list[TriggeredEffect]:
    """Return effects whose trigger and conditions match an event context.

    >>> effect = TriggeredEffect(
    ...     "gwm", "feature", "great_weapon_fighting", "damage_roll",
    ...     "reroll_matching_dice", {"damage_types_any": ["slashing"]}
    ... )
    >>> matching_effects(
    ...     [effect], "damage_roll", {"damage_types": ["slashing", "fire"]}
    ... ) == [effect]
    True
    """

    return [
        effect
        for effect in effects
        if effect.trigger == trigger and _conditions_match(effect.conditions, context)
    ]


def ability_modifier_contributions(
    effects: Iterable[TriggeredEffect],
    trigger: str,
    context: Mapping[str, object],
    ability_modifier: Callable[[str], int],
) -> tuple[TriggeredNumericContribution, ...]:
    """Resolve matching ``add_ability_modifier`` triggers with provenance.

    >>> effect = TriggeredEffect(
    ...     "agonizing_blast", "feature", "agonizing_blast|xphb",
    ...     "spell_damage_roll", "add_ability_modifier",
    ...     {"spell_id": "eldritch_blast"}, {"ability": "charisma"},
    ... )
    >>> ability_modifier_contributions(
    ...     (effect,), "spell_damage_roll", {"spell_id": "eldritch_blast"},
    ...     lambda ability: 3 if ability == "charisma" else 0,
    ... )[0].value
    3
    """

    contributions: list[TriggeredNumericContribution] = []
    for effect in matching_effects(effects, trigger, context):
        if effect.operation != "add_ability_modifier":
            continue
        ability = effect.parameters.get("ability")
        if not isinstance(ability, str):
            continue
        contributions.append(
            TriggeredNumericContribution(
                effect_id=effect.id,
                source_id=effect.source_id,
                value=ability_modifier(ability),
            )
        )
    return tuple(contributions)


def reroll_eligible_indices(
    effect: TriggeredEffect,
    pool: DicePoolResult,
) -> tuple[int, ...]:
    """Return dice that still satisfy a triggered reroll rule.

    >>> from srd_arena.domain.rolls.dice import DicePoolResult, DieRollResult
    >>> effect = TriggeredEffect(
    ...     "gwm", "feature", "great_weapon_fighting", "damage_roll",
    ...     "reroll_matching_dice", parameters={"values": [1, 2]}
    ... )
    >>> pool = DicePoolResult(
    ...     (DieRollResult(6, (1,)), DieRollResult(6, (5,))), 0, 6, 6
    ... )
    >>> reroll_eligible_indices(effect, pool)
    (0,)
    """

    if effect.operation != "reroll_matching_dice":
        return ()
    values = effect.parameters.get("values", [])
    if not isinstance(values, list):
        return ()
    qualifying_values = {value for value in values if isinstance(value, int)}
    maximum_per_die = effect.parameters.get("maximum_per_die", 1)
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
