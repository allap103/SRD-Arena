"""Verify the Scout's complete admitted combat behavior."""

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
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.geometry import Grid, Position
from srd_arena.domain.rolls.randomness import DiceRoller

BESTIARY = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)


def _scout(creature_id: str = "scout", *, size: str | None = None) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(
            {
                "id": creature_id,
                "size": size,
                "stat_block": {"name": "Scout", "source": "XMM"},
            }
        ),
        bestiary=BESTIARY,
    )


def _encounter(*, target_x: int = 2) -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "scout-test",
        EncounterDefinition(
            "scout-test",
            Grid(125, 4),
            teams=[
                EncounterTeam("scouts", "Scouts", ["scout"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "scout": EncounterCreatureState(
                "scout",
                _scout(),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                build_creature(
                    CreatureSchema.model_validate(
                        {
                            "id": "target",
                            "stat_block": {"name": "Ogre", "source": "XMM"},
                        }
                    ),
                    bestiary=BESTIARY,
                ),
                Position(target_x, 1),
                behavior,
            ),
        },
        initiative_order=["scout", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def _action(
    state: EncounterState,
    *,
    kind: str,
    name: str | None = None,
    attack_type: str | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, "scout")
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
        and (attack_type is None or action.preferred_attack_type == attack_type)
    )


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_scout_loads_supported_actions_and_core_statistics() -> None:
    scout = _scout()

    assert scout.size == "S"
    assert _scout("medium_scout", size="M").size == "M"
    assert scout.get_armor_class() == 13
    assert scout.get_max_health() == 16
    assert scout.attributes.movement.speed_feet == 30
    assert scout.statistics.creature_type == "humanoid"
    assert scout.statistics.skill_bonuses == {
        "nature": 4,
        "perception": 5,
        "stealth": 6,
        "survival": 5,
    }

    shortsword = scout.stat_block_actions["Shortsword"]
    longbow = scout.stat_block_actions["Longbow"]
    assert isinstance(shortsword, AttackActionDefinition)
    assert shortsword.attack_modes == ("melee",)
    assert shortsword.attack_bonus == 4
    assert shortsword.hit == (DamageEffect("1d6", 2, "piercing"),)
    assert stat_block_action_runtime_issue(shortsword) is None

    assert isinstance(longbow, AttackActionDefinition)
    assert longbow.attack_modes == ("ranged",)
    assert longbow.attack_bonus == 4
    assert longbow.range_normal_feet == 150
    assert longbow.range_long_feet == 600
    assert longbow.hit == (DamageEffect("1d8", 2, "piercing"),)
    assert stat_block_action_runtime_issue(longbow) is None

    assert scout.multiattack is not None
    [step] = scout.multiattack.plans[0].steps
    assert step.times == 2
    assert tuple(option.name for option in step.options) == (
        "Shortsword",
        "Longbow",
    )


def test_scout_multiattack_allows_any_two_authored_attacks() -> None:
    state = _encounter()
    target = state.creatures["target"].creature
    starting_health = target.get_health()

    execute_creature_action(
        state,
        _action(state, kind="multiattack"),
        state.current_decision(),
    )
    assert len(state.creatures["scout"].pending_multiattack) == 2

    execute_creature_action(
        state,
        _action(state, kind="attack", name="Shortsword"),
        state.current_decision(),
    )
    execute_creature_action(
        state,
        _action(
            state,
            kind="attack",
            name="Longbow",
            attack_type="ranged",
        ),
        state.current_decision(),
    )

    assert target.get_health() == starting_health - 6
    assert state.creatures["scout"].pending_multiattack == []


def test_scout_longbow_uses_normal_and_long_range_bands() -> None:
    normal_state = _encounter(target_x=31)
    long_state = _encounter(target_x=32)

    normal_result = execute_creature_action(
        normal_state,
        _action(
            normal_state,
            kind="attack",
            name="Longbow",
            attack_type="ranged",
        ),
        normal_state.current_decision(),
    )
    long_result = execute_creature_action(
        long_state,
        _action(
            long_state,
            kind="attack",
            name="Longbow",
            attack_type="ranged",
        ),
        long_state.current_decision(),
    )
    normal_event = next(
        event
        for event in normal_result.progress.events
        if event.type == "attack_resolved"
    )
    long_event = next(
        event
        for event in long_result.progress.events
        if event.type == "attack_resolved"
    )

    assert _mapping(normal_event.data["attack_roll_detail"])["mode"] == "normal"
    assert _mapping(long_event.data["attack_roll_detail"])["mode"] == "disadvantage"


def test_scout_longbow_is_unavailable_beyond_long_range() -> None:
    state = _encounter(target_x=122)

    assert not any(
        action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == "Longbow"
        for action in available_creature_actions(state, "scout")
    )
