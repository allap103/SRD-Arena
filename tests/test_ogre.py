"""Verify the Ogre's complete admitted combat behavior."""

from collections.abc import Mapping
from typing import cast

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures import AttackActionDefinition, Creature
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


def _encounter(*, target_x: int = 3) -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "ogre-test",
        EncounterDefinition(
            "ogre-test",
            Grid(30, 4),
            teams=[
                EncounterTeam("giants", "Giants", ["ogre"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "ogre": EncounterCreatureState(
                "ogre",
                _monster("ogre", "Ogre"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", "Goblin Warrior"),
                Position(target_x, 1),
                behavior,
            ),
        },
        initiative_order=["ogre", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _attack(
    state: EncounterState,
    attack_name: str,
    attack_type: str,
) -> dict[str, object]:
    action = next(
        action
        for action in available_creature_actions(state, "ogre")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == attack_name
        and action.preferred_attack_type == attack_type
    )
    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )
    return event.data


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_ogre_loads_supported_actions_and_core_statistics() -> None:
    ogre = _monster("ogre", "Ogre")

    assert ogre.size == "L"
    assert ogre.get_armor_class() == 11
    assert ogre.get_max_health() == 68
    assert ogre.attributes.movement.speed_feet == 40
    assert ogre.statistics.creature_type == "giant"
    assert ogre.sense_range("darkvision") == 60

    greatclub = ogre.stat_block_actions["Greatclub"]
    javelin = ogre.stat_block_actions["Javelin"]

    assert isinstance(greatclub, AttackActionDefinition)
    assert greatclub.attack_modes == ("melee",)
    assert greatclub.attack_bonus == 6
    assert greatclub.reach_feet == 5
    assert greatclub.hit == (DamageEffect("2d8", 4, "bludgeoning"),)
    assert stat_block_action_runtime_issue(greatclub) is None

    assert isinstance(javelin, AttackActionDefinition)
    assert javelin.attack_modes == ("melee", "ranged")
    assert javelin.attack_bonus == 6
    assert javelin.reach_feet == 5
    assert javelin.range_normal_feet == 30
    assert javelin.range_long_feet == 120
    assert javelin.hit == (DamageEffect("2d6", 4, "piercing"),)
    assert stat_block_action_runtime_issue(javelin) is None


def test_ogre_greatclub_and_melee_javelin_execute_through_runtime() -> None:
    greatclub_event = _attack(_encounter(), "Greatclub", "melee")
    javelin_event = _attack(_encounter(), "Javelin", "melee")

    assert greatclub_event["hit"] is True
    assert greatclub_event["damage"] == 6
    assert greatclub_event["attack_name"] == "Greatclub"
    assert javelin_event["hit"] is True
    assert javelin_event["damage"] == 6
    assert javelin_event["attack_name"] == "Javelin"


def test_ogre_javelin_uses_normal_and_long_range_bands() -> None:
    normal_event = _attack(_encounter(target_x=8), "Javelin", "ranged")
    long_event = _attack(_encounter(target_x=9), "Javelin", "ranged")

    assert normal_event["hit"] is True
    assert _mapping(normal_event["attack_roll_detail"])["mode"] == "normal"
    assert long_event["hit"] is True
    assert _mapping(long_event["attack_roll_detail"])["mode"] == "disadvantage"
