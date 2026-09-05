"""Verify the Animated Armor's complete SRD 5.2 combat behavior."""

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures import AttackActionDefinition, Creature
from srd_arena.domain.creatures.initiative import initiative_modifier
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
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
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


def _encounter() -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "animated-armor-test",
        EncounterDefinition(
            "animated-armor-test",
            Grid(8, 8),
            teams=[
                EncounterTeam("constructs", "Constructs", ["armor"], "external"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        {
            "armor": EncounterCreatureState(
                "armor",
                _monster("armor", "Animated Armor"),
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
        initiative_order=["armor", "target"],
        dice=DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1),
    )


def test_animated_armor_loads_complete_core_combat_rules() -> None:
    armor = _monster("armor", "Animated Armor")

    assert armor.size == "M"
    assert armor.attributes.movement.speed_feet == 25
    assert armor.get_armor_class() == 18
    assert armor.statistics.creature_type == "construct"
    assert armor.sense_range("blindsight") == 60
    assert armor.statistics.initiative_proficiency_multiplier == 1
    assert initiative_modifier(armor) == 2
    assert armor.statistics.damage_immunities == frozenset({"poison", "psychic"})
    assert armor.statistics.condition_immunities == frozenset(
        {
            Condition.CHARMED,
            Condition.DEAFENED,
            Condition.EXHAUSTION,
            Condition.FRIGHTENED,
            Condition.PARALYZED,
            Condition.PETRIFIED,
            Condition.POISONED,
        }
    )

    slam = armor.stat_block_actions["Slam"]
    assert isinstance(slam, AttackActionDefinition)
    assert slam.attack_modes == ("melee",)
    assert slam.attack_bonus == 4
    assert slam.reach_feet == 5
    assert slam.hit == (DamageEffect("1d6", 2, "bludgeoning"),)
    assert stat_block_action_runtime_issue(slam) is None
    assert armor.multiattack is not None
    sequence = armor.multiattack.executable_sequence({"Slam"})
    assert sequence is not None
    assert [entry.name for entry in sequence] == [
        "Slam",
        "Slam",
    ]


def test_animated_armor_multiattack_executes_two_slams() -> None:
    state = _encounter()
    target = state.creatures["target"].creature
    starting_health = target.get_health()

    multiattack = next(
        action
        for action in available_creature_actions(state, "armor")
        if action.kind == "multiattack"
    )
    execute_creature_action(state, multiattack, state.current_decision())

    assert state.creatures["armor"].attacks_remaining == 2
    resolved_attacks: list[CombatEvent] = []
    for _ in range(2):
        slam = next(
            action
            for action in available_creature_actions(state, "armor")
            if action.kind == "attack"
            and action.value == "target"
            and action.preferred_attack_name == "Slam"
        )
        result = execute_creature_action(state, slam, state.current_decision())
        resolved_attacks.extend(
            event for event in result.progress.events if event.type == "attack_resolved"
        )

    assert [event.data["attack_name"] for event in resolved_attacks] == [
        "Slam",
        "Slam",
    ]
    assert [event.data["damage"] for event in resolved_attacks] == [3, 3]
    assert target.get_health() == starting_health - 6
    assert state.creatures["armor"].attacks_remaining == 0
    assert state.creatures["armor"].pending_multiattack == []


def test_animated_armor_immunities_apply_through_runtime_queries() -> None:
    state = _encounter()

    assert apply_damage(state, "armor", 5, "poison") == 0
    assert apply_damage(state, "armor", 5, "psychic") == 0

    for condition in state.creatures["armor"].creature.statistics.condition_immunities:
        application = build_applied_condition(
            condition=condition,
            source_ref="target",
            source_label="Target",
            target_ref="armor",
            value=1 if condition is Condition.EXHAUSTION else None,
        )
        result = apply_condition(state, application)
        assert result.accepted is False
        assert result.rejections[0].reason == "condition_immunity"
