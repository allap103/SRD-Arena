"""Verify the Owlbear's complete admitted combat behavior."""

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


def _encounter() -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "owlbear-test",
        EncounterDefinition(
            "owlbear-test",
            Grid(10, 8),
            teams=[
                EncounterTeam(
                    "monstrosities", "Monstrosities", ["owlbear"], "external"
                ),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "owlbear": EncounterCreatureState(
                "owlbear",
                _monster("owlbear", "Owlbear"),
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                _monster("target", "Ogre"),
                Position(3, 1),
                behavior,
            ),
        },
        initiative_order=["owlbear", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def test_owlbear_loads_complete_core_combat_rules() -> None:
    owlbear = _monster("owlbear", "Owlbear")

    assert owlbear.size == "L"
    assert owlbear.get_armor_class() == 13
    assert owlbear.get_max_health() == 59
    assert owlbear.attributes.movement.speed_feet == 40
    assert owlbear.attributes.movement.climb_feet == 40
    assert owlbear.statistics.creature_type == "monstrosity"
    assert owlbear.statistics.skill_bonuses["perception"] == 5
    assert owlbear.sense_range("darkvision") == 60

    rend = owlbear.stat_block_actions["Rend"]
    assert isinstance(rend, AttackActionDefinition)
    assert rend.attack_modes == ("melee",)
    assert rend.attack_bonus == 7
    assert rend.reach_feet == 5
    assert rend.hit == (DamageEffect("2d8", 5, "slashing"),)
    assert stat_block_action_runtime_issue(rend) is None

    assert owlbear.multiattack is not None
    sequence = owlbear.multiattack.executable_sequence({"Rend"})
    assert sequence is not None
    assert tuple(invocation.name for invocation in sequence) == ("Rend", "Rend")


def test_owlbear_multiattack_executes_two_rend_attacks() -> None:
    state = _encounter()
    target = state.creatures["target"].creature
    starting_health = target.get_health()
    multiattack = next(
        action
        for action in available_creature_actions(state, "owlbear")
        if action.kind == "multiattack"
    )

    execute_creature_action(state, multiattack, state.current_decision())
    attack_names: list[str] = []
    for _ in range(2):
        attack = next(
            action
            for action in available_creature_actions(state, "owlbear")
            if action.kind == "attack"
            and action.value == "target"
            and action.preferred_attack_name == "Rend"
        )
        result = execute_creature_action(state, attack, state.current_decision())
        attack_names.extend(
            str(event.data["attack_name"])
            for event in result.progress.events
            if event.type == "attack_resolved"
        )

    assert attack_names == ["Rend", "Rend"]
    assert target.get_health() == starting_health - 14
    assert state.creatures["owlbear"].pending_multiattack == []
