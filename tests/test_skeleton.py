"""Verify the Skeleton's complete admitted combat behavior."""

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
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.actions.stat_block_runtime.validation import (
    stat_block_action_runtime_issue,
)
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.creature_control import execute_creature_action
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterTeam,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.rule_queries import apply_damage
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


def _encounter(*, target_x: int = 2) -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "skeleton-test",
        EncounterDefinition(
            "skeleton-test",
            Grid(70, 4),
            teams=[
                EncounterTeam("undead", "Undead", ["skeleton"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "skeleton": EncounterCreatureState(
                "skeleton",
                _monster("skeleton", "Skeleton"),
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
        initiative_order=["skeleton", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _attack(state: EncounterState, attack_name: str) -> dict[str, object]:
    action = next(
        action
        for action in available_creature_actions(state, "skeleton")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == attack_name
    )
    result = execute_creature_action(state, action, state.current_decision())
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )
    return event.data


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_skeleton_attacks_load_as_supported_typed_actions() -> None:
    skeleton = _monster("skeleton", "Skeleton")

    assert skeleton.size == "M"
    assert skeleton.attributes.movement.speed_feet == 30
    assert skeleton.statistics.creature_type == "undead"
    assert skeleton.sense_range("darkvision") == 60

    shortsword = skeleton.stat_block_actions["Shortsword"]
    shortbow = skeleton.stat_block_actions["Shortbow"]

    assert isinstance(shortsword, AttackActionDefinition)
    assert shortsword.attack_modes == ("melee",)
    assert shortsword.attack_bonus == 5
    assert shortsword.reach_feet == 5
    assert shortsword.hit == (DamageEffect("1d6", 3, "piercing"),)
    assert stat_block_action_runtime_issue(shortsword) is None

    assert isinstance(shortbow, AttackActionDefinition)
    assert shortbow.attack_modes == ("ranged",)
    assert shortbow.attack_bonus == 5
    assert shortbow.range_normal_feet == 80
    assert shortbow.range_long_feet == 320
    assert shortbow.hit == (DamageEffect("1d6", 3, "piercing"),)
    assert stat_block_action_runtime_issue(shortbow) is None


def test_skeleton_shortsword_executes_through_the_encounter_runtime() -> None:
    state = _encounter()

    event = _attack(state, "Shortsword")

    assert event["hit"] is True
    assert event["damage"] == 4
    assert event["attack_name"] == "Shortsword"


def test_skeleton_shortbow_uses_normal_and_long_range_bands() -> None:
    normal_event = _attack(_encounter(target_x=17), "Shortbow")
    long_event = _attack(_encounter(target_x=18), "Shortbow")

    assert normal_event["hit"] is True
    assert _mapping(normal_event["attack_roll_detail"])["mode"] == "normal"
    assert long_event["hit"] is True
    assert _mapping(long_event["attack_roll_detail"])["mode"] == "disadvantage"


def test_skeleton_defenses_apply_through_runtime_queries() -> None:
    state = _encounter()
    skeleton = state.creatures["skeleton"].creature

    assert apply_damage(state, "skeleton", 5, "poison") == 0
    assert apply_damage(state, "skeleton", 3, "bludgeoning") == 6
    assert skeleton.get_health() == 7

    for condition in (Condition.EXHAUSTION, Condition.POISONED):
        application = build_applied_condition(
            condition=condition,
            source_ref="target",
            source_label="Target",
            target_ref="skeleton",
            value=1 if condition is Condition.EXHAUSTION else None,
        )
        result = apply_condition(state, application)
        assert result.accepted is False
        assert result.rejections[0].reason == "condition_immunity"
