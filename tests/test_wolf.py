"""Verify the Wolf's authored Bite and size-gated knockdown."""

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import ConditionEffect, DamageEffect, SizeRequirement
from srd_arena.domain.creatures import AttackActionDefinition, Creature
from srd_arena.domain.effects.conditions import Condition
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


def _encounter(*, target_size: str = "M") -> EncounterState:
    wolf = _monster("wolf", "Wolf")
    target = _monster("target", "Goblin Warrior")
    target.size = target_size
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "wolf-test",
        EncounterDefinition(
            "wolf-test",
            Grid(8, 8),
            teams=[
                EncounterTeam("wolves", "Wolves", ["wolf"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "wolf": EncounterCreatureState(
                "wolf",
                wolf,
                Position(1, 1),
                behavior,
            ),
            "target": EncounterCreatureState(
                "target",
                target,
                Position(2, 1),
                behavior,
            ),
        },
        initiative_order=["wolf", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def test_wolf_bite_loads_as_a_supported_typed_attack() -> None:
    wolf = _monster("wolf", "Wolf")

    bite = wolf.stat_block_actions["Bite"]

    assert isinstance(bite, AttackActionDefinition)
    assert bite.hit == (
        DamageEffect("1d6", 2, "piercing"),
        ConditionEffect(
            "prone",
            requirements=(SizeRequirement(maximum="M"),),
        ),
    )
    assert stat_block_action_runtime_issue(bite) is None


def test_wolf_bite_knocks_a_medium_target_prone_after_a_hit() -> None:
    state = _encounter()
    bite = next(
        action
        for action in available_creature_actions(state, "wolf")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == "Bite"
    )

    result = execute_creature_action(state, bite, state.current_decision())

    assert state.has_condition("target", Condition.PRONE)
    [prone] = state.conditions_for("target")
    assert prone.source_ref == "wolf"
    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )
    assert event.data["hit"] is True


def test_wolf_bite_does_not_knock_a_large_target_prone() -> None:
    state = _encounter(target_size="L")
    bite = next(
        action
        for action in available_creature_actions(state, "wolf")
        if action.kind == "attack"
        and action.value == "target"
        and action.preferred_attack_name == "Bite"
    )

    result = execute_creature_action(state, bite, state.current_decision())

    event = next(
        event for event in result.progress.events if event.type == "attack_resolved"
    )
    assert event.data["hit"] is True
    assert state.has_condition("target", Condition.PRONE) is False
