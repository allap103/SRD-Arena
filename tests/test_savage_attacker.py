"""Verify Savage Attacker's optional once-per-turn weapon damage choice."""

from collections.abc import Iterator
from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.encounters.participants import creature_controller
from srd_arena.domain.encounters.turn_lifecycle import advance_turn
from srd_arena.domain.geometry import Position
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    keep_alert_initiative,
    use_deterministic_dice,
)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _prepared_session(
    *,
    external_barbarian: bool,
    roll_values: tuple[int, ...] = (15, 1, 1, 6, 6, 15, 3, 3),
) -> tuple[Session, Iterator[int]]:
    """Place the canonical Barbarian beside the durable Ogre target."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "barbarian"
    )
    participant.controller = "external" if external_barbarian else "scripted"
    state.turn.index = state.initiative_order.index("barbarian")
    # This fixture isolates the post-hit feat after the first-roll choice.
    state.creatures["barbarian"].attack_rolls_made_this_turn = 1
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(5, 4)
    state.creatures["warlock"].position = Position(0, 0)
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position = Position(9, index * 2)
    rolls = iter(roll_values)
    use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))
    return session, rolls


def _maul_attack_id(session: Session) -> str:
    """Return the advertised Maul attack against the training Ogre."""

    return next(
        option.id
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Maul"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
    )


def test_savage_attacker_rolls_weapon_damage_twice_and_uses_either_pool() -> None:
    """Delay damage until the external Barbarian chooses one complete pool."""

    session, _rolls = _prepared_session(external_barbarian=True)
    state = session.encounter_state
    assert state is not None
    ogre = state.creatures["ogre_target"].creature
    initial_health = ogre.get_health()

    attack = session._choose(_maul_attack_id(session))

    assert state.current_decision().kind == "reroll_dice"
    assert ogre.get_health() == initial_health
    assert any(event.type == "attack_pending" for event in attack.events)
    choices = session._read().action_options
    assert [option.kind for option in choices if option.kind != "system_exit"] == [
        "reroll_damage_pool",
        "accept_roll",
    ]

    rerolled = session._choose(
        next(option.id for option in choices if option.kind == "reroll_damage_pool")
    )

    assert ogre.get_health() == initial_health
    assert state.creatures["barbarian"].features_used_this_turn == {"savage_attacker"}
    reroll_event = next(
        event for event in rerolled.events if event.type == "damage_rerolled"
    )
    assert reroll_event.data["original_damage_total"] == 6
    assert reroll_event.data["alternate_damage_total"] == 16
    selection = session._read().action_options
    assert [
        option.label for option in selection if option.kind == "select_damage_roll"
    ] == ["Use second damage roll (16)", "Use original damage roll (6)"]

    resolved = session._choose(
        next(
            option.id
            for option in selection
            if option.label == "Use second damage roll (16)"
        )
    )

    assert ogre.get_health() == initial_health - 16
    selected = next(
        event for event in resolved.events if event.type == "damage_roll_selected"
    )
    assert selected.data == {
        "feature_id": "savage_attacker",
        "selected_attempt": 1,
        "selected_total": 16,
    }

    second = session._choose(_maul_attack_id(session))
    assert state.current_decision().kind == "turn"
    assert ogre.get_health() == initial_health - 26
    assert not any(event.type == "attack_pending" for event in second.events)

    advance_turn(state)
    assert state.creatures["barbarian"].features_used_this_turn == set()


def test_declining_savage_attacker_preserves_its_once_per_turn_option() -> None:
    """Offer the feature again after the character keeps the first damage roll."""

    session, _rolls = _prepared_session(
        external_barbarian=True,
        roll_values=(15, 1, 1, 15, 3, 3),
    )
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))
    accept = next(
        option
        for option in session._read().action_options
        if option.kind == "accept_roll"
    )

    session._choose(accept.id)

    assert state.creatures["barbarian"].features_used_this_turn == set()
    session._choose(_maul_attack_id(session))
    assert state.current_decision().kind == "reroll_dice"


def test_scripted_barbarian_resolves_savage_attacker_through_same_decision() -> None:
    """Let the scripted ally roll again and select the higher advertised pool."""

    session, _rolls = _prepared_session(external_barbarian=False)
    state = session.encounter_state
    assert state is not None
    assert creature_controller(state, "barbarian") == "scripted"
    initial_health = state.creatures["ogre_target"].creature.get_health()

    opened = session.advance_one_automatic_action()
    assert state.current_decision().kind == "reroll_dice"
    assert any(event.type == "attack_pending" for event in opened.events)

    rerolled = session.advance_one_automatic_action()
    assert state.current_decision().kind == "reroll_dice"
    assert any(event.type == "damage_rerolled" for event in rerolled.events)

    selected = session.advance_one_automatic_action()
    assert state.current_decision().kind == "turn"
    assert state.creatures["ogre_target"].creature.get_health() == initial_health - 16
    assert any(event.type == "damage_roll_selected" for event in selected.events)
