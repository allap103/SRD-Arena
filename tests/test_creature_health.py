from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import make_creature
from srd_arena.domain.effects.modifiers import DamageReduction, RollModifier
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters.actions.attack_resolution import resolve_attack
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw


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


def test_same_spell_roll_modifiers_do_not_stack() -> None:
    creature = make_creature()
    bless = (RollModifier(roll="attack_roll", mode="add", dice="1d4"),)
    creature.set_roll_modifiers("bless", "first", bless)
    creature.set_roll_modifiers("bless", "second", bless)

    rolls: list[int] = []

    def roller(sides: int) -> int:
        rolls.append(sides)
        return 4

    assert creature.resolve_roll_modifiers("attack_roll", roller) == 4
    assert rolls == [4]

    creature.remove_roll_modifiers("bless", "first")
    assert creature.resolve_roll_modifiers("attack_roll", roller) == 4


def test_sourced_modifiers_feed_central_attack_and_save_resolution() -> None:
    creature = make_creature()
    target = make_creature()
    creature.set_roll_modifiers(
        "bless",
        "cast",
        (
            RollModifier(roll="attack_roll", mode="add", value=2),
            RollModifier(roll="saving_throw", mode="add", value=3),
        ),
    )

    attack = resolve_attack(
        creature,
        target,
        "Attacker",
        "Target",
        d20_roller=lambda _sides: 10,
    )
    save = resolve_saving_throw(
        creature,
        "constitution",
        10,
        roller=lambda _sides: 10,
    )

    assert attack.attack_roll_detail["sourced_modifier"] == 2
    assert save.modifiers.other == 3


def test_roll_mode_modifiers_expose_own_and_incoming_modes() -> None:
    creature = make_creature()
    creature.set_roll_modifiers(
        "foresight",
        "cast",
        (
            RollModifier(roll="attack_roll", mode="advantage"),
            RollModifier(
                roll="attack_roll",
                mode="disadvantage",
                subject="attacks_against_target",
            ),
        ),
    )

    assert creature.roll_mode("attack_roll") == "advantage"
    assert creature.incoming_attack_roll_mode() == "disadvantage"


def test_same_spell_armor_class_modifiers_do_not_stack() -> None:
    creature = make_creature()
    base = creature.get_armor_class()
    creature.set_armor_class_modifier("shield_of_faith", "first", 2)
    creature.set_armor_class_modifier("shield_of_faith", "second", 2)

    assert creature.get_armor_class() == base + 2

    creature.remove_armor_class_modifier("shield_of_faith", "first")
    assert creature.get_armor_class() == base + 2
    creature.remove_armor_class_modifier("shield_of_faith", "second")
    assert creature.get_armor_class() == base


def test_sourced_speed_modifiers_stack_by_definition() -> None:
    creature = make_creature()
    base = creature.effective_speed_feet()
    creature.set_speed_modifier("longstrider", "first", 10)
    creature.set_speed_modifier("longstrider", "second", 10)
    creature.set_speed_modifier("ray_of_frost", "ray", -10)

    assert creature.effective_speed_feet() == base

    creature.remove_speed_modifier("ray_of_frost", "ray")
    assert creature.effective_speed_feet() == base + 10


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
