"""Verify the Brown Bear's actions, knockdown, and Climb Speed."""

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import ConditionEffect, DamageEffect, SizeRequirement
from srd_arena.domain.creatures import AttackActionDefinition, Creature
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


def _combat_encounter(*, target_size: str = "L") -> EncounterState:
    target = _monster("target", "Ogre")
    target.size = target_size
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "brown-bear-test",
        EncounterDefinition(
            "brown-bear-test",
            Grid(10, 8),
            teams=[
                EncounterTeam("beasts", "Beasts", ["bear"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "bear": EncounterCreatureState(
                "bear",
                _monster("bear", "Brown Bear"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                target,
                Position(3, 1),
                behavior,
            ),
        },
        initiative_order=["bear", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _movement_encounter(monster_name: str) -> EncounterState:
    terrain = tuple(
        TerrainCell(
            Position(x, y),
            movement_mode=TerrainMovementMode.CLIMB,
        )
        for x in range(4, 12)
        for y in range(2)
    )
    behavior = EncounterBehavior(type="wait")
    creature = _monster("mover", monster_name)
    return EncounterState(
        "climb-test",
        EncounterDefinition(
            "climb-test",
            Grid(12, 3),
            teams=[EncounterTeam("movers", "Movers", ["mover"], "external")],
            terrain=terrain,
        ),
        {
            "mover": EncounterCreatureState(
                "mover",
                creature,
                Position(0, 0),
                behavior,
            )
        },
        initiative_order=["mover"],
        dice=DiceRoller(die_roller=lambda _sides: 10),
    )


def _move_right(state: EncounterState) -> None:
    action = next(
        action
        for action in available_creature_actions(state, "mover")
        if action.kind == "move" and action.value == "right"
    )
    execute_creature_action(state, action, state.current_decision())


def test_brown_bear_loads_supported_actions_and_core_statistics() -> None:
    bear = _monster("bear", "Brown Bear")

    assert bear.size == "L"
    assert bear.get_armor_class() == 11
    assert bear.attributes.movement.speed_feet == 40
    assert bear.attributes.movement.climb_feet == 30
    assert bear.statistics.creature_type == "beast"
    assert bear.statistics.skill_bonuses["perception"] == 3
    assert bear.sense_range("darkvision") == 60

    bite = bear.stat_block_actions["Bite"]
    claw = bear.stat_block_actions["Claw"]
    assert isinstance(bite, AttackActionDefinition)
    assert bite.hit == (DamageEffect("1d8", 3, "piercing"),)
    assert isinstance(claw, AttackActionDefinition)
    assert claw.hit == (
        DamageEffect("1d4", 3, "slashing"),
        ConditionEffect("prone", requirements=(SizeRequirement(maximum="L"),)),
    )
    assert stat_block_action_runtime_issue(bite) is None
    assert stat_block_action_runtime_issue(claw) is None


def test_brown_bear_multiattack_executes_bite_then_claw_and_knocks_prone() -> None:
    state = _combat_encounter()
    target = state.creatures["target"].creature
    starting_health = target.get_health()
    multiattack = next(
        action
        for action in available_creature_actions(state, "bear")
        if action.kind == "multiattack"
    )

    execute_creature_action(state, multiattack, state.current_decision())
    attack_names: list[str] = []
    for expected_name in ("Bite", "Claw"):
        attack = next(
            action
            for action in available_creature_actions(state, "bear")
            if action.kind == "attack"
            and action.value == "target"
            and action.preferred_attack_name == expected_name
        )
        result = execute_creature_action(state, attack, state.current_decision())
        attack_names.extend(
            str(event.data["attack_name"])
            for event in result.progress.events
            if event.type == "attack_resolved"
        )

    assert attack_names == ["Bite", "Claw"]
    assert target.get_health() == starting_health - 8
    assert state.has_condition("target", Condition.PRONE)


def test_brown_bear_claw_does_not_knock_a_huge_target_prone() -> None:
    state = _combat_encounter(target_size="H")
    claw = next(
        action
        for action in available_creature_actions(state, "bear")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == "Claw"
    )

    execute_creature_action(state, claw, state.current_decision())

    assert state.has_condition("target", Condition.PRONE) is False


def test_brown_bear_switches_from_walk_to_its_shorter_climb_speed() -> None:
    state = _movement_encounter("Brown Bear")

    for _ in range(6):
        _move_right(state)

    mover = state.creatures["mover"]
    assert mover.position == Position(6, 0)
    assert mover.movement_mode == "climb"
    assert mover.movement_remaining == 0
    assert not any(
        action.kind == "move" and action.value == "right"
        for action in available_creature_actions(state, "mover")
    )


def test_creature_without_climb_speed_pays_extra_movement() -> None:
    state = _movement_encounter("Ogre")

    for _ in range(5):
        _move_right(state)

    mover = state.creatures["mover"]
    assert mover.position == Position(5, 0)
    assert mover.movement_remaining == 0
    assert not any(
        action.kind == "move" and action.value == "right"
        for action in available_creature_actions(state, "mover")
    )
