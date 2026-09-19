"""Verify the Hobgoblin Warrior's complete admitted combat behavior."""

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
from srd_arena.domain.creatures.initiative import initiative_modifier
from srd_arena.domain.effects import AdjacentAllyAttackAdvantage
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


def _encounter(*, target_x: int = 2, target_name: str = "Ogre") -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "hobgoblin-warrior-test",
        EncounterDefinition(
            "hobgoblin-warrior-test",
            Grid(125, 4),
            teams=[
                EncounterTeam("warriors", "Warriors", ["hobgoblin"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "hobgoblin": EncounterCreatureState(
                "hobgoblin",
                _monster("hobgoblin", "Hobgoblin Warrior"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", target_name),
                Position(target_x, 1),
                behavior,
            ),
        },
        initiative_order=["hobgoblin", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _attack(
    state: EncounterState,
    name: str,
    attack_type: str,
) -> tuple[EncounterAction, dict[str, object]]:
    action = next(
        action
        for action in available_creature_actions(state, "hobgoblin")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == name
        and action.preferred_attack_type == attack_type
    )
    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )
    return action, event.data


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_hobgoblin_warrior_loads_complete_core_combat_rules() -> None:
    warrior = _monster("hobgoblin", "Hobgoblin Warrior")

    assert warrior.size == "M"
    assert warrior.get_armor_class() == 18
    assert warrior.get_max_health() == 11
    assert warrior.attributes.movement.speed_feet == 30
    assert warrior.statistics.creature_type == "fey"
    assert warrior.statistics.type_tags == ("goblinoid",)
    assert warrior.sense_range("darkvision") == 60
    assert warrior.statistics.initiative_proficiency_multiplier == 1
    assert initiative_modifier(warrior) == 3
    provider = warrior.combat_profile.intrinsic_rule_providers["pack_tactics"]
    assert provider.rule_effects == (AdjacentAllyAttackAdvantage(5),)

    longsword = warrior.stat_block_actions["Longsword"]
    longbow = warrior.stat_block_actions["Longbow"]
    assert isinstance(longsword, AttackActionDefinition)
    assert longsword.attack_modes == ("melee",)
    assert longsword.attack_bonus == 3
    assert longsword.reach_feet == 5
    assert longsword.hit == (DamageEffect("2d10", 1, "slashing"),)
    assert stat_block_action_runtime_issue(longsword) is None

    assert isinstance(longbow, AttackActionDefinition)
    assert longbow.attack_modes == ("ranged",)
    assert longbow.attack_bonus == 3
    assert longbow.range_normal_feet == 150
    assert longbow.range_long_feet == 600
    assert longbow.hit == (
        DamageEffect("1d8", 1, "piercing"),
        DamageEffect("3d4", 0, "poison"),
    )
    assert stat_block_action_runtime_issue(longbow) is None


def test_hobgoblin_attacks_execute_and_poison_immunity_is_component_scoped() -> None:
    sword_state = _encounter()
    sword_target = sword_state.creatures["target"].creature
    sword_health = sword_target.get_health()
    _, sword_event = _attack(sword_state, "Longsword", "melee")

    assert sword_event["damage"] == 3
    assert sword_target.get_health() == sword_health - 3

    bow_state = _encounter(target_name="Skeleton")
    bow_target = bow_state.creatures["target"].creature
    bow_health = bow_target.get_health()
    _, bow_event = _attack(bow_state, "Longbow", "ranged")

    assert bow_event["damage"] == 2
    assert bow_target.get_health() == bow_health - 2


def test_hobgoblin_longbow_uses_normal_and_long_range_bands() -> None:
    normal_state = _encounter(target_x=31)
    long_state = _encounter(target_x=32)

    _, normal_event = _attack(normal_state, "Longbow", "ranged")
    _, long_event = _attack(long_state, "Longbow", "ranged")

    assert _mapping(normal_event["attack_roll_detail"])["mode"] == "normal"
    assert _mapping(long_event["attack_roll_detail"])["mode"] == "disadvantage"


def test_hobgoblin_longbow_is_unavailable_beyond_long_range() -> None:
    state = _encounter(target_x=122)

    assert not any(
        action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == "Longbow"
        for action in available_creature_actions(state, "hobgoblin")
    )
