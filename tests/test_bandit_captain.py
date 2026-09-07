"""Verify the Bandit Captain's complete admitted combat behavior."""

from typing import cast

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    Creature,
    ParryReactionDefinition,
)
from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.actions.options import decision_actions
from srd_arena.domain.encounters.creature_control import execute_creature_action
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterTeam,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.resolution import ParryRequest
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.reaction_runtime.parry import apply_parry_action
from srd_arena.domain.encounters.state_initialization import (
    initialize_action_selectors,
)
from srd_arena.domain.geometry import Grid, MovementBudget, Position
from srd_arena.domain.rolls.randomness import DiceRoller

BESTIARY = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)


def _monster(
    creature_id: str,
    name: str,
    *,
    size: str | None = None,
) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(
            {
                "id": creature_id,
                "size": size,
                "stat_block": {"name": name, "source": "XMM"},
            }
        ),
        bestiary=BESTIARY,
    )


def _encounter(*, captain_controller: str = "external") -> EncounterState:
    behavior = EncounterBehavior(type="wait")
    state = EncounterState(
        "bandit-captain-test",
        EncounterDefinition(
            "bandit-captain-test",
            Grid(8, 5),
            teams=[
                EncounterTeam("attackers", "Attackers", ["attacker"], "external"),
                EncounterTeam(
                    "captains",
                    "Captains",
                    ["captain"],
                    captain_controller,
                ),
            ],
        ),
        {
            "attacker": EncounterCreatureState(
                "attacker",
                _monster("attacker", "Goblin Warrior"),
                Position(1, 1),
                behavior,
            ),
            "captain": EncounterCreatureState(
                "captain",
                _monster("captain", "Bandit Captain"),
                Position(2, 1),
                behavior,
            ),
        },
        initiative_order=["attacker", "captain"],
        dice=DiceRoller(die_roller=lambda sides: 11 if sides == 20 else 1),
    )
    initialize_action_selectors(state)
    return state


def _attack(
    state: EncounterState,
    *,
    name: str,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, "attacker")
        if action.kind == "attack"
        and action.value == "captain"
        and action.preferred_attack_name == name
    )


def _captain_action(
    state: EncounterState,
    *,
    kind: str,
    name: str | None = None,
) -> EncounterAction:
    return next(
        action
        for action in available_creature_actions(state, "captain")
        if action.kind == kind
        and (name is None or action.preferred_attack_name == name)
    )


def _use_or_decline_parry(
    state: EncounterState,
    *,
    kind: str,
) -> None:
    decision = state.current_decision()
    action = next(action for action in decision_actions(state) if action.kind == kind)
    result = apply_parry_action(state, action, decision)
    assert result.completed is True


def test_bandit_captain_loads_attacks_multiattack_and_parry() -> None:
    captain = _monster("captain", "Bandit Captain")

    assert captain.size == "S"
    assert _monster("medium-captain", "Bandit Captain", size="M").size == "M"
    assert captain.get_armor_class() == 15
    assert captain.get_max_health() == 52
    assert captain.attributes.movement.speed_feet == 30
    assert captain.statistics.creature_type == "humanoid"
    assert captain.statistics.saving_throw_bonuses == {
        "strength": 4,
        "dexterity": 5,
        "wisdom": 2,
    }
    assert captain.statistics.skill_bonuses == {"athletics": 4, "deception": 4}

    scimitar = captain.stat_block_actions["Scimitar"]
    pistol = captain.stat_block_actions["Pistol"]
    parry = captain.stat_block_actions["Parry"]
    assert isinstance(scimitar, AttackActionDefinition)
    assert scimitar.hit == (DamageEffect("1d6", 3, "slashing"),)
    assert isinstance(pistol, AttackActionDefinition)
    assert pistol.range_normal_feet == 30
    assert pistol.range_long_feet == 90
    assert pistol.hit == (DamageEffect("1d10", 3, "piercing"),)
    assert parry == ParryReactionDefinition("Parry", 2, ("melee",))

    assert captain.multiattack is not None
    plans = captain.multiattack.plans
    assert len(plans) == 1
    assert len(plans[0].steps) == 1
    step = plans[0].steps[0]
    assert tuple(option.name for option in step.options) == (
        "Scimitar",
        "Pistol",
    )
    assert step.times == 2


def test_parry_can_turn_an_exact_melee_hit_into_a_miss() -> None:
    state = _encounter()
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()

    attack = execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )
    decision = state.current_decision()

    assert attack.progress.paused_for_decision is True
    assert decision.kind == "parry"
    assert isinstance(decision.request, ParryRequest)
    assert decision.request.attack.attack_roll == 15
    assert decision.request.would_prevent_hit is True
    assert captain.creature.get_health() == starting_health

    _use_or_decline_parry(state, kind="use_parry")

    assert captain.reaction_available is False
    assert captain.creature.get_health() == starting_health


def test_bandit_captain_multiattack_allows_any_two_authored_attacks() -> None:
    state = _encounter()
    state.turn.index = state.initiative_order.index("captain")
    state.dice = DiceRoller(die_roller=lambda sides: 19 if sides == 20 else 1)
    target = state.creatures["attacker"].creature
    starting_health = target.get_health()

    execute_creature_action(
        state,
        _captain_action(state, kind="multiattack"),
        state.current_decision(),
    )
    assert len(state.creatures["captain"].pending_multiattack) == 2

    execute_creature_action(
        state,
        _captain_action(state, kind="attack", name="Scimitar"),
        state.current_decision(),
    )
    execute_creature_action(
        state,
        _captain_action(state, kind="attack", name="Pistol"),
        state.current_decision(),
    )

    assert target.get_health() == starting_health - 8
    assert state.creatures["captain"].pending_multiattack == []


def test_declining_parry_preserves_reaction_and_applies_damage() -> None:
    state = _encounter()
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()
    execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )

    _use_or_decline_parry(state, kind="decline_parry")

    assert captain.reaction_available is True
    assert captain.creature.get_health() == starting_health - 3


def test_parry_can_be_spent_even_when_the_attack_still_hits() -> None:
    state = _encounter()
    state.dice = DiceRoller(die_roller=lambda sides: 14 if sides == 20 else 1)
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()
    execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )
    request = cast(ParryRequest, state.current_decision().request)

    assert request.attack.attack_roll == 18
    assert request.would_prevent_hit is False
    assert [action.kind for action in decision_actions(state)] == [
        "decline_parry",
        "use_parry",
    ]

    _use_or_decline_parry(state, kind="use_parry")

    assert captain.reaction_available is False
    assert captain.creature.get_health() == starting_health - 3


def test_parry_does_not_trigger_for_a_ranged_attack() -> None:
    state = _encounter()
    state.creatures["attacker"].position = Position(0, 1)
    state.creatures["captain"].position = Position(3, 1)
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()

    result = execute_creature_action(
        state,
        _attack(state, name="Shortbow"),
        state.current_decision(),
    )

    assert result.progress.paused_for_decision is False
    assert state.current_decision().kind == "turn"
    assert captain.creature.get_health() == starting_health - 3
    assert captain.reaction_available is True


def test_spent_reaction_prevents_a_second_parry_offer() -> None:
    state = _encounter()
    captain = state.creatures["captain"]
    captain.reaction_available = False
    starting_health = captain.creature.get_health()

    result = execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )

    assert result.progress.paused_for_decision is False
    assert captain.creature.get_health() == starting_health - 3


def test_scripted_bandit_captain_uses_parry_when_it_prevents_the_hit() -> None:
    state = _encounter(captain_controller="scripted")
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()
    execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )

    progress = EncounterOrchestrator().advance_one_action(state)

    assert any(
        event.type == "parry_resolved"
        and event.data["used"] is True
        and event.data["prevented_hit"] is True
        for event in progress.events
    )
    assert captain.creature.get_health() == starting_health
    assert captain.reaction_available is False


def test_scripted_bandit_captain_preserves_parry_when_it_cannot_prevent_hit() -> None:
    state = _encounter(captain_controller="scripted")
    state.dice = DiceRoller(die_roller=lambda sides: 14 if sides == 20 else 1)
    captain = state.creatures["captain"]
    starting_health = captain.creature.get_health()
    execute_creature_action(
        state,
        _attack(state, name="Scimitar"),
        state.current_decision(),
    )

    progress = EncounterOrchestrator().advance_one_action(state)

    assert any(
        event.type == "parry_resolved" and event.data["used"] is False
        for event in progress.events
    )
    assert captain.creature.get_health() == starting_health - 3
    assert captain.reaction_available is True


def test_parry_nests_inside_an_opportunity_attack_then_resumes_movement() -> None:
    state = _encounter()
    state.turn.index = state.initiative_order.index("captain")
    captain = state.creatures["captain"]
    captain.movement_remaining = MovementBudget(6)
    starting_health = captain.creature.get_health()
    orchestrator = EncounterOrchestrator()
    move = next(
        action
        for action in available_creature_actions(state, "captain")
        if action.kind == "move" and action.value == "right"
    )

    orchestrator.submit(state, move)
    opportunity = next(
        action
        for action in decision_actions(state)
        if action.kind == "opportunity_attack"
    )
    orchestrator.submit(state, opportunity)

    assert [frame.kind for frame in state.interrupts.decision_stack] == [
        "reaction",
        "parry",
    ]
    use_parry = next(
        action for action in decision_actions(state) if action.kind == "use_parry"
    )
    resumed = orchestrator.submit(state, use_parry)

    assert state.interrupts.decision_stack == []
    assert captain.position == Position(3, 1)
    assert captain.creature.get_health() == starting_health
    assert captain.reaction_available is False
    assert state.creatures["attacker"].reaction_available is False
    assert any(event.type == "movement_resolved" for event in resumed.events)
