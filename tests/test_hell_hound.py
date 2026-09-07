"""Verify the Hell Hound's complete SRD 5.2 combat behavior."""

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import DamageEffect, RechargePool
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    Creature,
    SavingThrowActionDefinition,
)
from srd_arena.domain.effects.rule_effects import AdjacentAllyAttackAdvantage
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
from srd_arena.domain.encounters.encounter import ActionCost, EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
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


def _encounter(*, die_result: int = 1) -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "hell-hound-test",
        EncounterDefinition(
            "hell-hound-test",
            Grid(8, 8),
            teams=[
                EncounterTeam(
                    "hounds",
                    "Hounds",
                    ["hound", "hound_ally"],
                    "external",
                ),
                EncounterTeam(
                    "targets",
                    "Targets",
                    ["target", "second_target"],
                    "external",
                ),
            ],
        ),
        {
            "hound": EncounterCreatureState(
                "hound",
                _monster("hound", "Hell Hound"),
                Position(1, 3),
                behavior,
            ),
            "hound_ally": EncounterCreatureState(
                "hound_ally",
                _monster("hound_ally", "Hell Hound"),
                Position(3, 5),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", "Ogre"),
                Position(2, 3),
                behavior,
            ),
            "second_target": EncounterCreatureState(
                "second_target",
                _monster("second_target", "Ogre"),
                Position(4, 2),
                behavior,
            ),
        },
        initiative_order=["hound", "hound_ally", "target", "second_target"],
        dice=DiceRoller(
            die_roller=lambda sides: die_result if sides == 20 else 1,
        ),
    )


def _action(
    state: EncounterState,
    *,
    kind: str,
    name: str | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, "hound")
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
    )


def _fire_breath_action() -> EncounterAction:
    return EncounterAction(
        label="Fire Breath",
        kind="stat_block",
        value=(5.5, 3.5),
        id="hound-fire-breath",
        creature_ref="hound",
        preferred_attack_name="Fire Breath {@recharge 5}",
        cost=ActionCost(action=1),
    )


def test_hell_hound_loads_complete_combat_definition() -> None:
    hound = _monster("hound", "Hell Hound")

    assert hound.size == "M"
    assert hound.get_armor_class() == 15
    assert hound.get_max_health() == 58
    assert hound.attributes.movement.speed_feet == 50
    assert hound.statistics.creature_type == "fiend"
    assert hound.statistics.skill_bonuses == {"perception": 5}
    assert hound.sense_range("darkvision") == 60
    assert hound.statistics.damage_immunities == frozenset({"fire"})
    assert hound.combat_profile.intrinsic_rule_providers[
        "pack_tactics"
    ].rule_effects == (AdjacentAllyAttackAdvantage(5),)

    bite = hound.stat_block_actions["Bite"]
    breath = hound.stat_block_actions["Fire Breath {@recharge 5}"]
    assert isinstance(bite, AttackActionDefinition)
    assert bite.attack_bonus == 5
    assert bite.hit == (
        DamageEffect("1d8", 3, "piercing"),
        DamageEffect("1d6", 0, "fire"),
    )
    assert stat_block_action_runtime_issue(bite) is None

    assert isinstance(breath, SavingThrowActionDefinition)
    assert breath.ability == "dex"
    assert breath.dc == 12
    assert breath.target.kind == "area"
    assert breath.target.shape == "cone"
    assert breath.target.size_feet == 15
    assert breath.failure[0].effects == (DamageEffect("5d6", 0, "fire"),)
    assert breath.success_damage == "half"
    assert breath.resource_pool == RechargePool(
        "stat_block_action:Fire Breath {@recharge 5}",
        6,
        5,
    )
    assert stat_block_action_runtime_issue(breath) is None

    assert hound.multiattack is not None
    [step] = hound.multiattack.plans[0].steps
    assert step.times == 2
    assert tuple(option.name for option in step.options) == ("Bite",)


def test_pack_tactics_applies_to_hell_hound_bite() -> None:
    state = _encounter()

    assert (
        attack_roll_mode_for(
            state,
            "hound",
            "target",
            "melee",
            state.creatures["hound"].position,
            (),
        )
        == "advantage"
    )


def test_hell_hound_multiattack_executes_two_bites() -> None:
    state = _encounter(die_result=19)
    target = state.creatures["target"].creature
    starting_health = target.get_health()

    execute_creature_action(
        state,
        _action(state, kind="multiattack"),
        state.current_decision(),
    )
    for _ in range(2):
        execute_creature_action(
            state,
            _action(state, kind="attack", name="Bite"),
            state.current_decision(),
        )

    assert target.get_health() == starting_health - 10


@pytest.mark.parametrize(
    ("saving_throw_roll", "damage_roll", "expected_damage"),
    [(1, 1, 5), (20, 6, 15)],
)
def test_fire_breath_hits_every_creature_in_cone_and_halves_on_success(
    saving_throw_roll: int,
    damage_roll: int,
    expected_damage: int,
) -> None:
    state = _encounter()
    state.dice = DiceRoller(
        die_roller=lambda sides: saving_throw_roll if sides == 20 else damage_roll
    )
    health_before = {
        creature_ref: state.creatures[creature_ref].creature.get_health()
        for creature_ref in ("target", "second_target")
    }

    execute_creature_action(
        state,
        _fire_breath_action(),
        state.current_decision(),
    )

    assert all(
        state.creatures[creature_ref].creature.get_health()
        == health_before[creature_ref] - expected_damage
        for creature_ref in ("target", "second_target")
    )
    assert (
        state.creatures["hound"].creature.stat_block_action_resources[
            "Fire Breath {@recharge 5}"
        ]
        == 0
    )
