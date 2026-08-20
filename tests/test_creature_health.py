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


def test_same_definition_maximum_health_modifiers_do_not_stack() -> None:
    creature = make_creature()
    base_maximum = creature.get_max_health()
    base_current = creature.get_health()

    creature.set_maximum_health_modifier(
        "aid", "first", 5, also_modify_current=True
    )
    creature.set_maximum_health_modifier(
        "aid", "second", 10, also_modify_current=True
    )

    assert creature.get_max_health() == base_maximum + 10
    assert creature.get_health() == base_current + 10
    creature.remove_maximum_health_modifier(
        "aid", "second", also_modify_current=True
    )
    assert creature.get_max_health() == base_maximum + 5
    assert creature.get_health() == base_current + 5
    creature.remove_maximum_health_modifier(
        "aid", "first", also_modify_current=True
    )
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
