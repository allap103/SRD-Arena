"""Verify the Giant Spider's complete admitted combat behavior."""

from collections.abc import Mapping, Sequence
from typing import cast

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import (
    CapabilityTarget,
    ConditionEffect,
    DamageEffect,
    DestructibleCondition,
    RechargePool,
)
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    Creature,
    SavingThrowActionDefinition,
)
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters import TerrainCell, TerrainMovementMode
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.actions.stat_block import (
    recharge_stat_block_actions,
)
from srd_arena.domain.encounters.actions.stat_block_runtime.validation import (
    stat_block_action_runtime_issue,
)
from srd_arena.domain.encounters.creature_control import execute_creature_action
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterTeam,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.geometry import Grid, Position
from srd_arena.domain.rolls.randomness import DiceRoller

BESTIARY = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)


def _monster(creature_id: str, name: str) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(
            {
                "id": creature_id,
                "stat_block": {"name": name, "source": "XMM"},
            }
        ),
        bestiary=BESTIARY,
    )


def _combat_encounter(*, target_name: str = "Goblin Warrior") -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "giant-spider-test",
        EncounterDefinition(
            "giant-spider-test",
            Grid(16, 5),
            teams=[
                EncounterTeam("beasts", "Beasts", ["spider"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "spider": EncounterCreatureState(
                "spider",
                _monster("spider", "Giant Spider"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", target_name),
                Position(3, 1),
                behavior,
            ),
        },
        initiative_order=["spider", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _movement_encounter() -> EncounterState:
    terrain = tuple(
        TerrainCell(
            Position(x, y),
            movement_mode=TerrainMovementMode.CLIMB,
        )
        for x in range(4, 12)
        for y in range(2)
    )
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "giant-spider-climb-test",
        EncounterDefinition(
            "giant-spider-climb-test",
            Grid(12, 3),
            teams=[EncounterTeam("beasts", "Beasts", ["spider"], "external")],
            terrain=terrain,
        ),
        {
            "spider": EncounterCreatureState(
                "spider",
                _monster("spider", "Giant Spider"),
                Position(0, 0),
                behavior,
            )
        },
        initiative_order=["spider"],
        dice=DiceRoller(die_roller=lambda _sides: 10),
    )


def _set_turn(state: EncounterState, creature_ref: str) -> None:
    state.turn.index = state.initiative_order.index(creature_ref)
    actor = state.creatures[creature_ref]
    actor.actions_remaining = 1
    actor.attacks_remaining = 0
    actor.attack_action_base_attacks = 0
    actor.attack_action_attacks_used = 0
    actor.attack_rolls_made_this_turn = 0


def _action(
    state: EncounterState,
    creature_ref: str,
    *,
    kind: str,
    name: str | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, creature_ref)
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
    )


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    assert isinstance(value, Sequence)
    return cast(Sequence[object], value)


def test_giant_spider_loads_supported_actions_and_core_statistics() -> None:
    spider = _monster("spider", "Giant Spider")

    assert spider.size == "L"
    assert spider.get_armor_class() == 14
    assert spider.get_max_health() == 26
    assert spider.attributes.movement.speed_feet == 30
    assert spider.attributes.movement.climb_feet == 30
    assert spider.statistics.creature_type == "beast"
    assert spider.statistics.skill_bonuses == {"perception": 4, "stealth": 7}
    assert spider.sense_range("darkvision") == 60

    bite = spider.stat_block_actions["Bite"]
    web = spider.stat_block_actions["Web {@recharge 5}"]

    assert isinstance(bite, AttackActionDefinition)
    assert bite.attack_bonus == 5
    assert bite.hit == (
        DamageEffect("1d8", 3, "piercing"),
        DamageEffect("2d6", 0, "poison"),
    )
    assert stat_block_action_runtime_issue(bite) is None

    assert isinstance(web, SavingThrowActionDefinition)
    assert web.ability == "dex"
    assert web.dc == 13
    assert web.target.range_feet == 60
    assert web.target.line_of_sight is True
    assert web.failure[0].effects == (
        ConditionEffect(
            "restrained",
            destructible=DestructibleCondition(
                "Web",
                10,
                5,
                ("fire",),
                ("poison", "psychic"),
            ),
        ),
    )
    assert web.resource_pool == RechargePool(
        "stat_block_action:Web {@recharge 5}",
        6,
        5,
    )
    assert stat_block_action_runtime_issue(web) is None


def test_giant_spider_bite_applies_piercing_and_poison_damage() -> None:
    state = _combat_encounter()
    starting_health = state.creatures["target"].creature.get_health()

    result = execute_creature_action(
        state,
        _action(state, "spider", kind="attack", name="Bite"),
        state.current_decision(),
    )
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )

    assert event.data["damage"] == 6
    assert state.creatures["target"].creature.get_health() == starting_health - 6


def test_giant_spider_bite_respects_poison_immunity() -> None:
    state = _combat_encounter(target_name="Skeleton")
    starting_health = state.creatures["target"].creature.get_health()

    result = execute_creature_action(
        state,
        _action(state, "spider", kind="attack", name="Bite"),
        state.current_decision(),
    )
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )

    assert event.data["damage"] == 4
    assert state.creatures["target"].creature.get_health() == starting_health - 4


def test_failed_web_save_applies_attackable_restrained_condition() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)

    result = execute_creature_action(
        state,
        _action(state, "spider", kind="stat_block", name="Web {@recharge 5}"),
        state.current_decision(),
    )
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    outcome = _mapping(_sequence(event.data["outcomes"])[0])
    applied = next(
        condition
        for condition in state.conditions_for("target")
        if condition.condition is Condition.RESTRAINED
    )

    assert outcome["success"] is False
    assert outcome["applied_conditions"] == ["restrained"]
    assert applied.source_ref == "spider"
    assert applied.destructible is not None
    assert applied.destructible.hit_points == 5
    assert applied.destructible.maximum_hit_points == 5
    assert applied.destructible.damage_vulnerabilities == frozenset({"fire"})
    assert applied.destructible.damage_immunities == frozenset({"poison", "psychic"})
    assert (
        state.creatures["spider"].creature.stat_block_action_resources[
            "Web {@recharge 5}"
        ]
        == 0
    )


def test_successful_web_save_prevents_restrained_condition() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 20)

    execute_creature_action(
        state,
        _action(state, "spider", kind="stat_block", name="Web {@recharge 5}"),
        state.current_decision(),
    )

    assert state.has_condition("target", Condition.RESTRAINED) is False


def test_web_recharges_only_on_five_or_six() -> None:
    spider = _monster("spider", "Giant Spider")
    spider.stat_block_action_resources["Web {@recharge 5}"] = 0

    recharge_stat_block_actions(spider, lambda _sides: 4)
    assert spider.stat_block_action_resources["Web {@recharge 5}"] == 0

    recharge_stat_block_actions(spider, lambda _sides: 5)
    assert spider.stat_block_action_resources["Web {@recharge 5}"] == 1


def test_web_damage_immunity_is_applied_per_damage_type() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)
    execute_creature_action(
        state,
        _action(state, "spider", kind="stat_block", name="Web {@recharge 5}"),
        state.current_decision(),
    )
    state.dice = DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1)
    _set_turn(state, "spider")

    result = execute_creature_action(
        state,
        _action(state, "spider", kind="attack_condition", name="Bite"),
        state.current_decision(),
    )
    event = next(
        event
        for event in result.progress.events
        if event.type == "destructible_condition_attacked"
    )
    remaining = next(
        condition
        for condition in state.conditions_for("target")
        if condition.condition is Condition.RESTRAINED
    )

    assert event.data["damage"] == 4
    assert remaining.destructible is not None
    assert remaining.destructible.hit_points == 1


def test_web_fire_vulnerability_doubles_damage() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)
    execute_creature_action(
        state,
        _action(state, "spider", kind="stat_block", name="Web {@recharge 5}"),
        state.current_decision(),
    )
    target = state.creatures["target"].creature
    target.stat_block_actions = {
        "Flame": AttackActionDefinition(
            name="Flame",
            attack_modes=("melee",),
            attack_bonus=5,
            target=CapabilityTarget("creature", range_feet=5),
            reach_feet=5,
            range_normal_feet=None,
            range_long_feet=None,
            hit=(DamageEffect("1d4", 2, "fire"),),
        )
    }
    target.stat_block_action_resources = {}
    state.dice = DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1)
    _set_turn(state, "target")

    result = execute_creature_action(
        state,
        _action(state, "target", kind="attack_condition", name="Flame"),
        state.current_decision(),
    )
    event = next(
        event
        for event in result.progress.events
        if event.type == "destructible_condition_attacked"
    )

    assert event.data["damage"] == 6
    assert event.data["destroyed"] is True
    assert state.has_condition("target", Condition.RESTRAINED) is False


def test_attacking_web_reduces_its_hp_then_removes_only_that_condition() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)
    execute_creature_action(
        state,
        _action(state, "spider", kind="stat_block", name="Web {@recharge 5}"),
        state.current_decision(),
    )
    state.dice = DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1)
    _set_turn(state, "target")

    first = execute_creature_action(
        state,
        _action(state, "target", kind="attack_condition", name="Scimitar"),
        state.current_decision(),
    )
    first_event = next(
        event
        for event in first.progress.events
        if event.type == "destructible_condition_attacked"
    )
    remaining = next(
        condition
        for condition in state.conditions_for("target")
        if condition.condition is Condition.RESTRAINED
    )

    assert first_event.data["damage"] == 3
    assert first_event.data["destroyed"] is False
    assert remaining.destructible is not None
    assert remaining.destructible.hit_points == 2

    _set_turn(state, "target")
    second = execute_creature_action(
        state,
        _action(state, "target", kind="attack_condition", name="Scimitar"),
        state.current_decision(),
    )
    second_event = next(
        event
        for event in second.progress.events
        if event.type == "destructible_condition_attacked"
    )

    assert second_event.data["destroyed"] is True
    assert second_event.data["remaining_hit_points"] == 0
    assert state.has_condition("target", Condition.RESTRAINED) is False


def test_giant_spider_uses_its_climb_speed_in_climb_terrain() -> None:
    state = _movement_encounter()

    for _ in range(6):
        execute_creature_action(
            state,
            next(
                action
                for action in available_creature_actions(state, "spider")
                if action.kind == "move" and action.value == "right"
            ),
            state.current_decision(),
        )

    spider = state.creatures["spider"]
    assert spider.position == Position(6, 0)
    assert spider.movement_mode == "climb"
    assert spider.movement_remaining == 0
