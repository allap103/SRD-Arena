"""Verify Javelin Slow through the shared Weapon Mastery lifecycle."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.rule_effects import SpeedAdjustment
from srd_arena.domain.effects.runtime import UntilTurnStart
from srd_arena.domain.encounters.actions.weapon_mastery import (
    mastery_request_for_attack,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_start import (
    expire_ongoing_effects_for_turn_start,
)
from srd_arena.domain.encounters.encounter_models.decisions import (
    WeaponMasteryRequest,
)
from srd_arena.domain.encounters.encounter_models.resolution import AttackOutcome
from srd_arena.domain.encounters.rule_queries.numeric import (
    effective_speed,
    movement_budget,
)
from srd_arena.domain.geometry import MovementBudget, MovementCost, Position
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    keep_alert_initiative,
    use_deterministic_dice,
)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _prepared_session(d20_rolls: tuple[int, ...]) -> Session:
    """Give the level-five Barbarian a Javelin target within normal range."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    barbarian = state.creatures["barbarian"].creature
    barbarian.equipment = replace(
        barbarian.equipment,
        right_hand="javelin",
        left_hand=None,
    )
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "barbarian"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("barbarian")
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(9, 4)
    state.creatures["warlock"].position = Position(0, 8)
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position = Position(0, index * 2)
    state.creatures["barbarian"].attack_rolls_made_this_turn = 1
    state.creatures["barbarian"].features_used_this_turn.add("savage_attacker")
    rolls: Iterator[int] = iter(d20_rolls)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: next(rolls) if sides == 20 else 4,
    )
    return session


def _javelin_attack_id(session: Session) -> str:
    """Return the ranged Javelin attack against the training Ogre."""

    return next(
        option.id
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Javelin"
        and option.preferred_attack_type == "ranged"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
    )


def _choose_mastery(session: Session, kind: str) -> EngineOutcome:
    """Choose one advertised use-or-decline Weapon Mastery option."""

    return session._choose(
        next(
            option.id
            for option in session._read().action_options
            if option.kind == kind
        )
    )


def test_slow_reduces_speed_and_reconciles_movement_already_spent() -> None:
    """Apply ten feet of reduction without forgiving movement already spent."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    target = state.creatures["ogre_target"]
    base_speed = effective_speed(state, "ogre_target").value
    base_budget = movement_budget(state, "ogre_target").budget
    target.movement_spent_this_turn = MovementCost(2)
    target.movement_remaining = MovementBudget(int(base_budget) - 2)

    attack = session._choose(_javelin_attack_id(session))
    decision = state.current_decision()

    assert any(event.type == "decision_opened" for event in attack.events)
    assert decision.kind == "weapon_mastery"
    assert isinstance(decision.request, WeaponMasteryRequest)
    assert decision.request.mastery == "Slow"
    assert decision.request.save_dc is None

    result = _choose_mastery(session, "use_weapon_mastery")
    resolved = next(
        event for event in result.events if event.type == "weapon_mastery_resolved"
    )
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "weapon_mastery_slow"
    )

    assert effective_speed(state, "ogre_target").value == base_speed - 10
    assert target.movement_remaining == MovementBudget(int(base_budget) - 4)
    assert effect.target_refs == ("ogre_target",)
    assert effect.identity.source.applied_by_ref == "barbarian"
    assert effect.rule_effects == (SpeedAdjustment(-10),)
    assert effect.duration == UntilTurnStart("barbarian")
    assert resolved.data["speed_reduction_feet"] == 10


def test_slow_instances_do_not_stack_and_expire_independently() -> None:
    """Retain repeated hits while limiting their combined reduction to ten feet."""

    session = _prepared_session((15, 15))
    state = session.encounter_state
    assert state is not None
    base_speed = effective_speed(state, "ogre_target").value

    session._choose(_javelin_attack_id(session))
    _choose_mastery(session, "use_weapon_mastery")
    session._choose(_javelin_attack_id(session))
    _choose_mastery(session, "use_weapon_mastery")

    effects = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "weapon_mastery_slow"
    )
    assert len(effects) == 2
    assert effective_speed(state, "ogre_target").value == base_speed - 10

    expire_ongoing_effects_for_turn_start(state, "barbarian")

    assert not any(
        effect.identity.source.definition_id == "weapon_mastery_slow"
        for effect in state.ongoing_effects
    )
    assert effective_speed(state, "ogre_target").value == base_speed


def test_slow_can_be_declined_without_creating_an_effect() -> None:
    """Leave target Speed unchanged when the attacker declines Slow."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    base_speed = effective_speed(state, "ogre_target").value
    session._choose(_javelin_attack_id(session))

    result = _choose_mastery(session, "decline_weapon_mastery")

    assert effective_speed(state, "ogre_target").value == base_speed
    assert not any(
        effect.identity.source.definition_id == "weapon_mastery_slow"
        for effect in state.ongoing_effects
    )
    assert any(
        event.type == "weapon_mastery_resolved" and event.data["used"] is False
        for event in result.events
    )


def test_slow_requires_the_hit_to_deal_damage() -> None:
    """Do not offer Slow when defenses reduce the hit's applied damage to zero."""

    session = _prepared_session(())
    state = session.encounter_state
    assert state is not None
    attack = AttackOutcome(
        messages=[],
        hit=True,
        attack_roll=15,
        damage=0,
        defender_defeated=False,
        attack_roll_detail={},
        weapon_id="javelin",
        weapon_name="Javelin",
        weapon_mastery="Slow",
    )

    request = mastery_request_for_attack(
        state,
        attack,
        attacker_ref="barbarian",
        target_ref="ogre_target",
        action_id="attack-1",
    )

    assert request is None


def test_slow_from_an_opportunity_attack_limits_resumed_movement() -> None:
    """Reconcile a suspended move against Speed reduced by its reaction."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    goblin = state.creatures["goblin_1"]
    barbarian = state.creatures["barbarian"]
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "goblin_1"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("goblin_1")
    goblin.position = Position(4, 4)
    barbarian.position = Position(4, 5)
    barbarian.features_used_this_turn.add("savage_attacker")

    move = next(
        option
        for option in session._read().action_options
        if option.kind == "move" and option.label == "Move up"
    )
    interrupted = session._choose(move.id)

    assert state.current_decision().kind == "reaction"
    assert not any(event.type == "movement_resolved" for event in interrupted.events)
    opportunity_attack = next(
        option
        for option in session._read().action_options
        if option.kind == "opportunity_attack"
    )
    session._choose(opportunity_attack.id)

    assert state.current_decision().kind == "weapon_mastery"
    resolved = _choose_mastery(session, "use_weapon_mastery")

    assert goblin.position == Position(4, 3)
    assert goblin.movement_spent_this_turn == MovementCost(1)
    assert goblin.movement_remaining == MovementBudget(3)
    assert any(
        event.type == "movement_resolved" and event.data["resumed"] is True
        for event in resolved.events
    )


def test_slow_cancels_a_suspended_step_that_is_no_longer_affordable() -> None:
    """Keep the mover in place when Slow consumes its last movement budget."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    goblin = state.creatures["goblin_1"]
    barbarian = state.creatures["barbarian"]
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "goblin_1"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("goblin_1")
    goblin.position = Position(4, 4)
    barbarian.position = Position(4, 5)
    barbarian.features_used_this_turn.add("savage_attacker")
    move = next(
        option
        for option in session._read().action_options
        if option.kind == "move" and option.label == "Move up"
    )
    goblin.movement_spent_this_turn = MovementCost(4)
    goblin.movement_remaining = MovementBudget(2)

    session._choose(move.id)
    opportunity_attack = next(
        option
        for option in session._read().action_options
        if option.kind == "opportunity_attack"
    )
    session._choose(opportunity_attack.id)
    resolved = _choose_mastery(session, "use_weapon_mastery")

    assert goblin.position == Position(4, 4)
    assert goblin.movement_spent_this_turn == MovementCost(4)
    assert goblin.movement_remaining == MovementBudget(0)
    assert any(
        event.type == "movement_cancelled"
        and event.data["reason"] == "insufficient_movement"
        for event in resolved.events
    )


def test_scripted_opportunity_attack_uses_slow_without_a_decision_pause() -> None:
    """Resolve the same Slow effect automatically for the scripted Barbarian."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    goblin = state.creatures["goblin_1"]
    barbarian = state.creatures["barbarian"]
    for creature_ref, controller in (
        ("barbarian", "scripted"),
        ("goblin_1", "external"),
    ):
        participant = next(
            participant
            for participant in state.definition.participants
            if participant.creature_id == creature_ref
        )
        participant.controller = controller
    state.turn.index = state.initiative_order.index("goblin_1")
    goblin.position = Position(4, 4)
    barbarian.position = Position(4, 5)
    barbarian.features_used_this_turn.add("savage_attacker")
    move = next(
        option
        for option in session._read().action_options
        if option.kind == "move" and option.label == "Move up"
    )

    resolved = session._choose(move.id)

    assert state.current_decision().kind == "turn"
    assert state.current_decision().creature_ref == "goblin_1"
    assert goblin.position == Position(4, 3)
    assert effective_speed(state, "goblin_1").value == 20
    assert any(
        event.type == "weapon_mastery_resolved" and event.data["mastery"] == "Slow"
        for event in resolved.events
    )
