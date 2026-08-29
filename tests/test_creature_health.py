from hypothesis import given
from hypothesis import strategies as st

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


def test_heal_does_not_reduce_health_above_supplied_maximum() -> None:
    creature = make_creature()
    original_health = creature.get_health()

    restored = creature.heal(5, maximum_health=original_health - 5)

    assert restored == 0
    assert creature.get_health() == original_health


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

    restored = creature.heal(healing)

    assert restored >= 0
    assert 0 <= creature.get_health() <= creature.get_max_health()
