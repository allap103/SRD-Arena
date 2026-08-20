from dataclasses import dataclass
from typing import Literal

from ..rolls.dice import DieRoller

RollKind = Literal["ability_check", "attack_roll", "damage_roll", "saving_throw"]
ModifierMode = Literal["add", "subtract"]


@dataclass(frozen=True)
class RollModifier:
    roll: RollKind
    mode: ModifierMode
    dice: str | None = None
    value: int | None = None

    def resolve(self, roller: DieRoller) -> int:
        total = self.value or 0
        if self.dice is not None:
            count_text, sides_text = self.dice.casefold().split("d", 1)
            total += sum(roller(int(sides_text)) for _ in range(int(count_text)))
        return total if self.mode == "add" else -total
