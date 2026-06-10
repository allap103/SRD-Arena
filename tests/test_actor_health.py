from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import make_actor


def test_take_damage_reduces_current_health() -> None:
    actor = make_actor()

    applied_damage = actor.take_damage(3)

    assert applied_damage == 3
    assert actor.get_health() == actor.get_max_health() - 3


def test_heal_restores_missing_health_only() -> None:
    actor = make_actor()
    actor.take_damage(5)

    restored = actor.heal(2)

    assert restored == 2
    assert actor.get_health() == actor.get_max_health() - 3


@given(st.integers(min_value=0, max_value=100))
def test_take_damage_never_drops_health_below_zero(amount: int) -> None:
    actor = make_actor()

    actor.take_damage(amount)

    assert 0 <= actor.get_health() <= actor.get_max_health()


@given(
    st.integers(min_value=0, max_value=100),
    st.integers(min_value=0, max_value=100),
)
def test_healing_never_exceeds_max_health(damage: int, healing: int) -> None:
    actor = make_actor()
    actor.take_damage(damage)

    actor.heal(healing)

    assert 0 <= actor.get_health() <= actor.get_max_health()
