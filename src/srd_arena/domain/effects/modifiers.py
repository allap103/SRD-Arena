"""Define reusable adjustments to dice rolls and incoming damage."""

from dataclasses import dataclass
from typing import Literal, cast

from ..rolls.dice import D20RollMode, DieRoller

RollKind = Literal["ability_check", "attack_roll", "damage_roll", "saving_throw"]
ModifierMode = Literal["advantage", "disadvantage", "add", "subtract"]
ModifierSubject = Literal["target", "attacks_against_target"]


@dataclass(frozen=True)
class RollModifier:
    """Describe an adjustment matched to a particular roll context.

    A modifier either changes advantage state or contributes a fixed/dice-based
    numeric amount. Runtime effect state supplies its provenance separately.
    """

    roll: RollKind
    mode: ModifierMode
    dice: str | None = None
    value: int | None = None
    subject: ModifierSubject = "target"
    ignored_by_senses: tuple[str, ...] = ()
    ability: str | None = None

    def resolve(self, roller: DieRoller) -> int:
        """Resolve an additive or subtractive modifier.

        >>> RollModifier("saving_throw", "add", dice="1d4").resolve(lambda _: 3)
        3
        >>> RollModifier("attack_roll", "subtract", value=2).resolve(lambda _: 1)
        -2
        """
        if self.mode not in {"add", "subtract"}:
            return 0
        total = self.value or 0
        if self.dice is not None:
            count_text, sides_text = self.dice.casefold().split("d", 1)
            total += sum(roller(int(sides_text)) for _ in range(int(count_text)))
        return total if self.mode == "add" else -total

    @property
    def roll_mode(self) -> D20RollMode | None:
        """Return the advantage mode contributed by this modifier, if any.

        >>> RollModifier("attack_roll", "advantage").roll_mode
        'advantage'
        >>> RollModifier("attack_roll", "add", value=1).roll_mode is None
        True
        """
        if self.mode in {"advantage", "disadvantage"}:
            return cast(D20RollMode, self.mode)
        return None
