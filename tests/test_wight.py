"""Verify the Wight's complete admitted combat behavior."""

from collections.abc import Iterator, Mapping
from typing import cast

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import (
    DamageEffect,
    HitPointMaximumReductionEffect,
)
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    Creature,
    SavingThrowActionDefinition,
)
from srd_arena.domain.creatures.initiative import initiative_modifier
from srd_arena.domain.effects import EnvironmentalRollAdjustment
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterEnvironment,
    EncounterTeam,
)
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.actions.stat_block import (
    executable_multiattack_slot_plans,
    stat_block_action_runtime_issue,
)
from srd_arena.domain.encounters.creature_control import execute_creature_action
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.rule_queries.health import effective_maximum_health
from srd_arena.domain.encounters.rule_queries.rolls import roll_modifiers
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


def _encounter(
    *,
    sunlight: bool = False,
    rolls: Iterator[int] | None = None,
) -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    roller = (lambda _sides: next(rolls)) if rolls is not None else (lambda _sides: 1)
    return EncounterState(
        "wight-test",
        EncounterDefinition(
            "wight-test",
            Grid(125, 8),
            teams=[
                EncounterTeam("undead", "Undead", ["wight"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
            environment=EncounterEnvironment(sunlight=sunlight),
        ),
        {
            "wight": EncounterCreatureState(
                "wight",
                _monster("wight", "Wight"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", "Ogre"),
                Position(2, 1),
                behavior,
            ),
        },
        initiative_order=["wight", "target"],
        dice=DiceRoller(die_roller=roller),
    )


def _action(
    state: EncounterState,
    *,
    kind: str,
    name: str | None = None,
    plan_index: int | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, "wight")
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
        and (plan_index is None or action.value == str(plan_index))
    )


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_wight_loads_complete_admitted_combat_rules() -> None:
    wight = _monster("wight", "Wight")

    assert wight.size == "M"
    assert wight.get_armor_class() == 14
    assert wight.get_max_health() == 82
    assert wight.attributes.movement.speed_feet == 30
    assert wight.statistics.creature_type == "undead"
    assert wight.statistics.skill_bonuses == {"perception": 3, "stealth": 4}
    assert wight.sense_range("darkvision") == 60
    assert wight.statistics.initiative_proficiency_multiplier == 1
    assert initiative_modifier(wight) == 4
    assert wight.statistics.damage_resistances == frozenset({"necrotic"})
    assert wight.statistics.damage_immunities == frozenset({"poison"})
    assert wight.statistics.condition_immunities == frozenset(
        {Condition.EXHAUSTION, Condition.POISONED}
    )

    sword = wight.stat_block_actions["Necrotic Sword"]
    bow = wight.stat_block_actions["Necrotic Bow"]
    drain = wight.stat_block_actions["Life Drain"]
    assert isinstance(sword, AttackActionDefinition)
    assert sword.hit == (
        DamageEffect("1d8", 2, "slashing"),
        DamageEffect("1d8", 0, "necrotic"),
    )
    assert isinstance(bow, AttackActionDefinition)
    assert bow.range_normal_feet == 150
    assert bow.range_long_feet == 600
    assert bow.hit == (
        DamageEffect("1d8", 2, "piercing"),
        DamageEffect("1d8", 0, "necrotic"),
    )
    assert isinstance(drain, SavingThrowActionDefinition)
    assert drain.ability == "con"
    assert drain.dc == 13
    assert drain.failure[0].effects == (
        DamageEffect("1d8", 2, "necrotic"),
        HitPointMaximumReductionEffect("damage_taken"),
    )
    assert all(
        stat_block_action_runtime_issue(definition) is None
        for definition in (sword, bow, drain)
    )


def test_sunlight_sensitivity_applies_only_in_sunlight() -> None:
    shade = _encounter()
    sunlight = _encounter(sunlight=True)
    provider = sunlight.creatures[
        "wight"
    ].creature.combat_profile.intrinsic_rule_providers["sunlight_sensitivity"]

    assert all(
        isinstance(effect, EnvironmentalRollAdjustment)
        for effect in provider.rule_effects
    )
    assert roll_modifiers(shade, "wight", "attack_roll").mode == "normal"
    assert roll_modifiers(sunlight, "wight", "attack_roll").mode == "disadvantage"
    assert (
        roll_modifiers(sunlight, "wight", "ability_check", "strength").mode
        == "disadvantage"
    )
    assert roll_modifiers(sunlight, "wight", "saving_throw").mode == "normal"


def test_life_drain_reduces_maximum_hp_by_damage_taken_only_on_failure() -> None:
    failure = _encounter(rolls=iter((1, 4)))
    target = failure.creatures["target"].creature
    original_health = target.get_health()
    original_maximum = effective_maximum_health(failure, "target").value

    result = execute_creature_action(
        failure,
        _action(failure, kind="stat_block", name="Life Drain"),
        failure.current_decision(),
    )
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    [outcome] = cast(list[object], event.data["outcomes"])
    details = _mapping(outcome)

    assert details["damage"] == 6
    assert details["maximum_hit_point_reduction"] == 6
    assert target.get_health() == original_health - 6
    assert effective_maximum_health(failure, "target").value == original_maximum - 6
    assert failure.ongoing_effects[-1].dispellable is False

    success = _encounter(rolls=iter((19,)))
    success_target = success.creatures["target"].creature
    success_maximum = effective_maximum_health(success, "target").value
    execute_creature_action(
        success,
        _action(success, kind="stat_block", name="Life Drain"),
        success.current_decision(),
    )

    assert success_target.get_health() == success_maximum
    assert effective_maximum_health(success, "target").value == success_maximum
    assert success.ongoing_effects == []


def test_wight_multiattack_can_replace_either_attack_with_one_life_drain() -> None:
    state = _encounter(rolls=iter((1, 1, 19, 1, 1)))
    plans = executable_multiattack_slot_plans(state.creatures["wight"].creature)
    slot_names = [
        [[option.name for option in slot.options] for slot in plan] for plan in plans
    ]
    assert slot_names == [
        [
            ["Necrotic Sword", "Necrotic Bow"],
            ["Necrotic Sword", "Necrotic Bow"],
        ],
        [["Life Drain"], ["Necrotic Sword", "Necrotic Bow"]],
        [["Necrotic Sword", "Necrotic Bow"], ["Life Drain"]],
    ]

    execute_creature_action(
        state,
        _action(state, kind="multiattack", plan_index=1),
        state.current_decision(),
    )
    drain = _action(state, kind="stat_block", name="Life Drain")
    assert drain.cost.action == 0
    execute_creature_action(state, drain, state.current_decision())

    assert len(state.creatures["wight"].pending_multiattack) == 1
    assert not any(
        action.preferred_attack_name == "Life Drain"
        for action in available_creature_actions(state, "wight")
    )
    execute_creature_action(
        state,
        _action(state, kind="attack", name="Necrotic Sword"),
        state.current_decision(),
    )

    assert state.creatures["wight"].pending_multiattack == []
    assert state.creatures["wight"].attacks_remaining == 0
