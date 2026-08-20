from dataclasses import dataclass
from typing import Literal, cast

from ..rolls.dice import D20RollMode, DieRoller

RollKind = Literal["ability_check", "attack_roll", "damage_roll", "saving_throw"]
ModifierMode = Literal["advantage", "disadvantage", "add", "subtract"]
ModifierSubject = Literal["target", "attacks_against_target"]


@dataclass(frozen=True)
class RollModifier:
    roll: RollKind
    mode: ModifierMode
    dice: str | None = None
    value: int | None = None
    subject: ModifierSubject = "target"

    def resolve(self, roller: DieRoller) -> int:
        if self.mode not in {"add", "subtract"}:
            return 0
        total = self.value or 0
        if self.dice is not None:
            count_text, sides_text = self.dice.casefold().split("d", 1)
            total += sum(roller(int(sides_text)) for _ in range(int(count_text)))
        return total if self.mode == "add" else -total

    @property
    def roll_mode(self) -> D20RollMode | None:
        if self.mode in {"advantage", "disadvantage"}:
            return cast(D20RollMode, self.mode)
        return None


@dataclass
class DamageReduction:
    damage_type: str
    dice: str
    available: bool = True

    def resolve(self, roller: DieRoller) -> int:
        if not self.available:
            return 0
        count_text, sides_text = self.dice.casefold().split("d", 1)
        self.available = False
        return sum(roller(int(sides_text)) for _ in range(int(count_text)))
