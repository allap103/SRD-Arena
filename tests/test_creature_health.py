from hypothesis import given
from hypothesis import strategies as st

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.modifiers import DamageReduction
from tests.helpers import make_creature


def test_take_damage_reduces_current_health() -> None:
    creature = make_creature()

    applied_damage = creature.take_damage(3)

    assert applied_damage == 3
    assert creature.get_health() == creature.get_max_health() - 3


def test_heal_restores_missing_health_only() -> None:
    creature = make_creature()
    creature.take_damage(5)

    restored = creature.heal(2)

    assert restored == 2
    assert creature.get_health() == creature.get_max_health() - 3


def test_temporary_hit_points_absorb_damage_before_health() -> None:
    creature = make_creature()
    creature.grant_temporary_hit_points(5)

    applied = creature.take_damage(7)

    assert applied == 7
    assert creature.temporary_hit_points == 0
    assert creature.get_health() == creature.get_max_health() - 2


def test_temporary_hit_points_replace_only_a_smaller_pool() -> None:
    creature = make_creature()

    assert creature.grant_temporary_hit_points(5) == 5
    assert creature.grant_temporary_hit_points(3) == 0
    assert creature.temporary_hit_points == 5
    assert creature.grant_temporary_hit_points(8) == 3
    assert creature.temporary_hit_points == 8


def test_sourced_damage_resistance_halves_matching_damage() -> None:
    creature = make_creature()
    creature.add_damage_resistance("poison", "protection-cast")

    assert creature.take_damage(7, "poison") == 3
    assert creature.take_damage(7, "fire") == 7

    creature.remove_damage_resistance("poison", "protection-cast")
    assert creature.take_damage(2, "poison") == 2


def test_damage_reduction_is_used_once_per_turn_before_resistance() -> None:
    creature = make_creature()
    creature.set_damage_reduction(
        "resistance",
        "cast",
        DamageReduction(damage_type="fire", dice="1d4"),
    )
    creature.add_damage_resistance("fire", "another-effect")

    assert creature.take_damage(10, "fire", roller=lambda _sides: 4) == 3
    assert creature.take_damage(10, "fire", roller=lambda _sides: 4) == 5

    creature.reset_per_turn_modifiers()
    assert creature.take_damage(10, "fire", roller=lambda _sides: 2) == 4


def test_sourced_condition_immunity_does_not_remove_static_immunity() -> None:
    creature = make_creature()
    creature.set_condition_immunities(
        "heroism", "cast", frozenset({Condition.FRIGHTENED})
    )

    assert Condition.FRIGHTENED in creature.condition_immunities()

    creature.remove_condition_immunities("heroism", "cast")
    assert Condition.FRIGHTENED not in creature.condition_immunities()


def test_sourced_senses_extend_static_senses() -> None:
    attacker = make_creature()

    attacker.set_senses("true_seeing", "cast", (("truesight", 120),))
    assert attacker.sense_range("truesight") == 120

    attacker.remove_senses("true_seeing", "cast")
    assert attacker.sense_range("truesight") is None


def test_same_definition_maximum_health_modifiers_do_not_stack() -> None:
    creature = make_creature()
    base_maximum = creature.get_max_health()
    base_current = creature.get_health()

    creature.set_maximum_health_modifier("aid", "first", 5, also_modify_current=True)
    creature.set_maximum_health_modifier("aid", "second", 10, also_modify_current=True)

    assert creature.get_max_health() == base_maximum + 10
    assert creature.get_health() == base_current + 10
    creature.remove_maximum_health_modifier("aid", "second", also_modify_current=True)
    assert creature.get_max_health() == base_maximum + 5
    assert creature.get_health() == base_current + 5
    creature.remove_maximum_health_modifier("aid", "first", also_modify_current=True)
    assert creature.get_max_health() == base_maximum
    assert creature.get_health() == base_current


@given(st.integers(min_value=0, max_value=100))
def test_take_damage_never_drops_health_below_zero(amount: int) -> None:
    creature = make_creature()

    creature.take_damage(amount)

    assert 0 <= creature.get_health() <= creature.get_max_health()


@given(
    st.integers(min_value=0, max_value=100),
    st.integers(min_value=0, max_value=100),
)
def test_healing_never_exceeds_max_health(damage: int, healing: int) -> None:
    creature = make_creature()
    creature.take_damage(damage)

    creature.heal(healing)

    assert 0 <= creature.get_health() <= creature.get_max_health()
