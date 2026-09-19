"""Verify the canonical Barbarian's optional Reckless Attack lifecycle."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from srd_arena.content.character_options.classes import load_class_catalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.runtime import EffectSourceKind, UntilTurnStart
from srd_arena.domain.encounters.effect_lifecycle.turn_start import (
    expire_ongoing_effects_for_turn_start,
)
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.geometry import Position
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
    """Give the level-five Barbarian an externally controlled adjacent target."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    barbarian = state.creatures["barbarian"].creature
    assert barbarian.character_profile is not None
    barbarian.character_profile = replace(
        barbarian.character_profile,
        weapon_masteries=tuple(
            name
            for name in barbarian.character_profile.weapon_masteries
            if name != "Maul"
        ),
    )
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "barbarian"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("barbarian")
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(5, 4)
    state.creatures["barbarian"].features_used_this_turn.add("savage_attacker")
    rolls = iter(d20_rolls)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: next(rolls) if sides == 20 else 4,
    )
    return session


def _maul_attack_id(session: Session) -> str:
    """Return the canonical Barbarian's Maul attack against the Ogre."""

    return next(
        option.id
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Maul"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
    )


def _choose_reckless(session: Session) -> EngineOutcome:
    """Accept the currently offered Reckless Attack decision."""

    option = next(
        option
        for option in session._read().action_options
        if option.kind == "use_reckless_attack"
    )
    return session._choose(option.id)


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def test_reckless_attack_enters_progression_at_level_two() -> None:
    """Compile Reckless Attack only for level 2 and higher snapshots."""

    snapshots = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)
    level_one = build_creature(
        snapshots.creature_template("barbarian", 1),
        classes=classes,
    )
    level_two = build_creature(
        snapshots.creature_template("barbarian", 2),
        classes=classes,
    )

    assert all(feature.id != "reckless_attack" for feature in level_one.class_features)
    assert any(feature.id == "reckless_attack" for feature in level_two.class_features)


def test_reckless_attack_pauses_the_first_strength_attack_and_grants_advantage() -> (
    None
):
    """Apply the choice before rolling and preserve its sourced runtime state."""

    session = _prepared_session((2, 18))
    state = session.encounter_state
    assert state is not None

    opened = session._choose(_maul_attack_id(session))

    assert state.current_decision().kind == "reckless_attack"
    assert any(event.type == "decision_opened" for event in opened.events)
    resolved = _choose_reckless(session)
    attack = next(event for event in resolved.events if event.type == "attack_resolved")
    detail = _mapping(attack.data["attack_roll_detail"])
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "reckless_attack"
    )

    assert detail["dice"] == [2, 18]
    assert detail["mode"] == "advantage"
    assert state.creatures["barbarian"].attack_rolls_made_this_turn == 1
    assert effect.identity.source.kind is EffectSourceKind.FEATURE
    assert effect.duration == UntilTurnStart("barbarian", state.round.number + 1)


def test_reckless_attack_benefits_later_strength_attacks_and_exposes_the_user() -> None:
    """Keep both sides of the rule active until the Barbarian's next turn."""

    session = _prepared_session((3, 17, 4, 16))
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))
    _choose_reckless(session)

    second = session._choose(_maul_attack_id(session))
    attack = next(event for event in second.events if event.type == "attack_resolved")
    detail = _mapping(attack.data["attack_roll_detail"])
    incoming_mode = attack_roll_mode_for(
        state,
        "ogre_target",
        "barbarian",
        "melee",
        state.creatures["ogre_target"].position,
        (state.creatures["barbarian"].position,),
    )

    assert state.current_decision().kind != "reckless_attack"
    assert detail["dice"] == [4, 16]
    assert detail["mode"] == "advantage"
    assert incoming_mode == "advantage"
    assert state.creatures["barbarian"].attack_rolls_made_this_turn == 2


def test_declining_reckless_attack_does_not_offer_it_on_the_second_roll() -> None:
    """Consume the first-roll opportunity even when the feature is declined."""

    session = _prepared_session((12, 13))
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))
    decline = next(
        option
        for option in session._read().action_options
        if option.kind == "decline_reckless_attack"
    )

    first = session._choose(decline.id)
    first_attack = next(
        event for event in first.events if event.type == "attack_resolved"
    )
    second = session._choose(_maul_attack_id(session))
    second_attack = next(
        event for event in second.events if event.type == "attack_resolved"
    )

    assert _mapping(first_attack.data["attack_roll_detail"])["mode"] == "normal"
    assert _mapping(second_attack.data["attack_roll_detail"])["mode"] == "normal"
    assert state.current_decision().kind != "reckless_attack"
    assert state.creatures["barbarian"].attack_rolls_made_this_turn == 2


def test_non_strength_first_attack_consumes_the_reckless_opportunity() -> None:
    """Do not defer the first-roll gate until a later Strength attack."""

    session = _prepared_session((1, 1, 1))
    state = session.encounter_state
    assert state is not None
    barbarian = state.creatures["barbarian"].creature
    barbarian.equipment = replace(
        barbarian.equipment,
        right_hand="shortbow",
        left_hand=None,
    )
    shortbow = next(
        option
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Shortbow"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
    )

    session._choose(shortbow.id)
    barbarian.equipment = replace(barbarian.equipment, right_hand="maul")
    session._choose(_maul_attack_id(session))

    assert state.current_decision().kind != "reckless_attack"
    assert state.creatures["barbarian"].attack_rolls_made_this_turn == 2
    assert all(
        effect.identity.source.definition_id != "reckless_attack"
        for effect in state.ongoing_effects
    )


def test_reckless_attack_expires_at_the_start_of_the_next_turn() -> None:
    """Remove both advantage contributions at the exact turn-start boundary."""

    session = _prepared_session((4, 15))
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))
    _choose_reckless(session)
    state.round.number += 1

    expire_ongoing_effects_for_turn_start(state, "barbarian")

    assert all(
        effect.identity.source.definition_id != "reckless_attack"
        for effect in state.ongoing_effects
    )
