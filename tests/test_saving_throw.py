from dataclasses import dataclass

from srd_arena.domain.creatures import Attributes
from srd_arena.domain.rolls.dice import resolve_roll_attempts
from srd_arena.domain.rolls.saving_throws import (
    Ability,
    reroll_saving_throw,
    resolve_saving_throw,
)


@dataclass
class StubCreature:
    attributes: Attributes

    def get_modifier(self, attribute_value: int) -> int:
        return (attribute_value - 10) // 2

    def saving_throw_ability_score(self, ability: Ability) -> int:
        return {
            "strength": self.attributes.strength,
            "dexterity": self.attributes.dexterity,
            "constitution": self.attributes.constitution,
            "intelligence": self.attributes.intelligence,
            "wisdom": self.attributes.wisdom,
            "charisma": self.attributes.charisma,
        }[ability]

    @property
    def saving_throw_proficiency_bonus(self) -> int:
        return self.attributes.proficiency_bonus

    def is_saving_throw_proficient(self, ability: Ability) -> bool:
        return ability in self.attributes.saving_throw_proficiencies

    def explicit_saving_throw_bonus(self, ability: Ability) -> int | None:
        return None


def _actor() -> StubCreature:
    return StubCreature(
        Attributes(
            base_health=10,
            level=5,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=8,
            charisma=10,
            base_armor_class=10,
            saving_throw_proficiencies=frozenset({"strength", "constitution"}),
        )
    )


def test_resolve_saving_throw_applies_ability_proficiency_and_other_modifiers() -> None:
    result = resolve_saving_throw(
        _actor(),
        "strength",
        15,
        other_modifier=1,
        roller=lambda _sides: 8,
    )

    assert result.proficient is True
    assert result.modifiers.ability == 3
    assert result.modifiers.proficiency == 3
    assert result.modifiers.other == 1
    assert result.modifiers.total == 7
    assert result.check.roll.total == 15
    assert result.check.success is True


def test_resolve_saving_throw_supports_advantage_without_proficiency() -> None:
    rolls = iter([4, 17])

    result = resolve_saving_throw(
        _actor(),
        "dexterity",
        15,
        mode="advantage",
        roller=lambda _sides: next(rolls),
    )

    assert result.proficient is False
    assert result.modifiers.proficiency == 0
    assert result.check.roll.dice == (4, 17)
    assert result.check.roll.selected == 17
    assert result.check.success is True


def test_failed_saving_throw_can_be_rerolled_with_bonus_and_must_use_new_result() -> (
    None
):
    creature = _actor()
    original = resolve_saving_throw(
        creature,
        "wisdom",
        15,
        roller=lambda _sides: 10,
    )
    rerolled = reroll_saving_throw(
        creature,
        original,
        bonus_modifier=5,
        roller=lambda _sides: 12,
    )

    resolution = resolve_roll_attempts(
        [original, rerolled],
        selected_attempt=1,
        reason="indomitable",
    )

    assert original.check.success is False
    assert rerolled.check.target == original.check.target
    assert rerolled.modifiers.other == 5
    assert rerolled.check.success is True
    assert resolution.selected is rerolled
