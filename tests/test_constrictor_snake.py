"""Verify the Constrictor Snake's complete admitted combat behavior."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import ConditionEffect, DamageEffect, SizeRequirement
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
from srd_arena.domain.encounters.grappling_state import grappling_targets_for
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
        "constrictor-snake-test",
        EncounterDefinition(
            "constrictor-snake-test",
            Grid(12, 5),
            teams=[
                EncounterTeam("beasts", "Beasts", ["snake"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "snake": EncounterCreatureState(
                "snake",
                _monster("snake", "Constrictor Snake"),
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
        initiative_order=["snake", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _movement_encounter() -> EncounterState:
    terrain = tuple(
        TerrainCell(
            Position(x, y),
            movement_mode=TerrainMovementMode.SWIM,
        )
        for x in range(4, 12)
        for y in range(2)
    )
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "snake-swim-test",
        EncounterDefinition(
            "snake-swim-test",
            Grid(12, 3),
            teams=[EncounterTeam("beasts", "Beasts", ["snake"], "external")],
            terrain=terrain,
        ),
        {
            "snake": EncounterCreatureState(
                "snake",
                _monster("snake", "Constrictor Snake"),
                Position(0, 0),
                behavior,
            )
        },
        initiative_order=["snake"],
        dice=DiceRoller(die_roller=lambda _sides: 10),
    )


def _action(
    state: EncounterState,
    *,
    kind: str,
    name: str | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(
            state,
            state.current_decision().creature_ref,
        )
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
    )


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    assert isinstance(value, Sequence)
    return cast(Sequence[object], value)


def test_constrictor_snake_loads_supported_actions_and_core_statistics() -> None:
    snake = _monster("snake", "Constrictor Snake")

    assert snake.size == "L"
    assert snake.get_armor_class() == 13
    assert snake.get_max_health() == 13
    assert snake.attributes.movement.speed_feet == 30
    assert snake.attributes.movement.swim_feet == 30
    assert snake.statistics.creature_type == "beast"
    assert snake.statistics.skill_bonuses == {"perception": 2, "stealth": 4}
    assert snake.sense_range("blindsight") == 10

    bite = snake.stat_block_actions["Bite"]
    constrict = snake.stat_block_actions["Constrict"]

    assert isinstance(bite, AttackActionDefinition)
    assert bite.attack_bonus == 4
    assert bite.hit == (DamageEffect("1d8", 2, "piercing"),)
    assert stat_block_action_runtime_issue(bite) is None

    assert isinstance(constrict, SavingThrowActionDefinition)
    assert constrict.ability == "str"
    assert constrict.dc == 12
    assert constrict.target.line_of_sight is True
    assert constrict.target.requirements == (SizeRequirement(maximum="M"),)
    assert constrict.failure[0].effects == (
        DamageEffect("3d4", 0, "bludgeoning"),
        ConditionEffect("grappled", escape_dc=12, source_capacity=1),
    )
    assert stat_block_action_runtime_issue(constrict) is None


def test_constrictor_snake_bite_executes_through_runtime() -> None:
    state = _combat_encounter()
    action = _action(state, kind="attack", name="Bite")

    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )

    assert event.data["hit"] is True
    assert event.data["damage"] == 3


def test_failed_constrict_save_deals_damage_and_creates_escapable_grapple() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)
    target = state.creatures["target"].creature
    starting_health = target.get_health()
    action = _action(state, kind="stat_block", name="Constrict")

    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    outcome = _mapping(_sequence(event.data["outcomes"])[0])

    assert outcome["success"] is False
    assert outcome["damage"] == 3
    assert outcome["applied_conditions"] == ["grappled"]
    assert target.get_health() == starting_health - 3
    assert state.has_condition("target", Condition.GRAPPLED)
    assert grappling_targets_for(state, "snake") == ("target",)
    grapple = next(
        condition
        for condition in state.conditions_for("target")
        if condition.condition is Condition.GRAPPLED
    )
    assert grapple.source_ref == "snake"
    assert grapple.metadata["escape_dc"] == 12

    state.initiative_order = ["target", "snake"]
    state.turn.index = 0
    state.creatures["target"].actions_remaining = 1
    state.dice = DiceRoller(die_roller=lambda _sides: 20)
    escape = _action(state, kind="escape_grapple")

    escaped = execute_creature_action(state, escape, state.current_decision())

    assert state.has_condition("target", Condition.GRAPPLED) is False
    assert grappling_targets_for(state, "snake") == ()
    assert any("escapes" in message for _, message in escaped.progress.messages)


def test_successful_constrict_save_prevents_damage_and_grapple() -> None:
    state = _combat_encounter()
    target = state.creatures["target"].creature
    starting_health = target.get_health()
    action = _action(state, kind="stat_block", name="Constrict")

    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    outcome = _mapping(_sequence(event.data["outcomes"])[0])

    assert outcome["success"] is True
    assert outcome["damage"] == 0
    assert outcome["applied_conditions"] == []
    assert target.get_health() == starting_health
    assert state.has_condition("target", Condition.GRAPPLED) is False


def test_constrict_damage_applies_when_the_target_is_immune_to_grappled() -> None:
    state = _combat_encounter()
    state.dice = DiceRoller(die_roller=lambda _sides: 1)
    target = state.creatures["target"].creature
    target.statistics = replace(
        target.statistics,
        condition_immunities=frozenset({Condition.GRAPPLED}),
    )
    starting_health = target.get_health()
    action = _action(state, kind="stat_block", name="Constrict")

    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    outcome = _mapping(_sequence(event.data["outcomes"])[0])

    assert outcome["success"] is False
    assert outcome["damage"] == 3
    assert outcome["applied_conditions"] == []
    assert target.get_health() == starting_health - 3
    assert state.has_condition("target", Condition.GRAPPLED) is False


def test_constrict_is_not_available_against_a_large_target() -> None:
    state = _combat_encounter(target_name="Ogre")

    assert not any(
        action.kind == "stat_block" and action.preferred_attack_name == "Constrict"
        for action in available_creature_actions(state, "snake")
    )


def test_constrictor_snake_uses_its_swim_speed_in_swim_terrain() -> None:
    state = _movement_encounter()

    for _ in range(6):
        move_right = next(
            action
            for action in available_creature_actions(state, "snake")
            if action.kind == "move" and action.value == "right"
        )
        execute_creature_action(state, move_right, state.current_decision())

    snake = state.creatures["snake"]
    assert snake.position == Position(6, 0)
    assert snake.movement_mode == "swim"
    assert snake.movement_remaining == 0
