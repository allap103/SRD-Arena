"""Verify Maul Topple through the public encounter decision lifecycle."""

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters.encounter_models.decisions import (
    WeaponMasteryRequest,
)
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


def _prepared_session(
    d20_rolls: tuple[int, ...],
    *,
    suppress_savage_attacker: bool = True,
) -> Session:
    """Give the level-five Barbarian an adjacent externally controlled target."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "barbarian"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("barbarian")
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(5, 4)
    state.creatures["barbarian"].attack_rolls_made_this_turn = 1
    if suppress_savage_attacker:
        state.creatures["barbarian"].features_used_this_turn.add("savage_attacker")
    rolls: Iterator[int] = iter(d20_rolls)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: next(rolls) if sides == 20 else 4,
    )
    return session


def _maul_attack_id(session: Session) -> str:
    """Return the Maul attack that addresses the adjacent Ogre target."""

    return next(
        option.id
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Maul"
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


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow structured event data for focused assertions."""

    return cast(Mapping[str, object], value)


def test_topple_uses_attack_ability_and_proficiency_for_its_save_dc() -> None:
    """Offer DC 15 from Strength +4 and proficiency +3 after the Maul hits."""

    session = _prepared_session((15, 1))
    state = session.encounter_state
    assert state is not None

    attack = session._choose(_maul_attack_id(session))
    decision = state.current_decision()

    assert any(event.type == "decision_opened" for event in attack.events)
    assert decision.kind == "weapon_mastery"
    assert isinstance(decision.request, WeaponMasteryRequest)
    assert decision.request.mastery == "Topple"
    assert decision.request.save_dc == 15

    result = _choose_mastery(session, "use_weapon_mastery")
    mastery = next(
        event for event in result.events if event.type == "weapon_mastery_resolved"
    )

    assert _mapping(mastery.data)["save_succeeded"] is False
    assert _mapping(mastery.data)["condition_applied"] is True
    assert any(
        applied.condition is Condition.PRONE
        and applied.target_ref == "ogre_target"
        and applied.identity.source.definition_id == "topple"
        and applied.source_ref == "barbarian"
        for applied in state.conditions
    )


def test_topple_successful_save_does_not_apply_prone() -> None:
    """Resolve the target's Constitution save through the normal save rules."""

    session = _prepared_session((15, 20))
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))

    result = _choose_mastery(session, "use_weapon_mastery")
    mastery = next(
        event for event in result.events if event.type == "weapon_mastery_resolved"
    )

    assert _mapping(mastery.data)["save_succeeded"] is True
    assert _mapping(mastery.data)["condition_applied"] is False
    assert not any(
        applied.condition is Condition.PRONE and applied.target_ref == "ogre_target"
        for applied in state.conditions
    )


def test_topple_can_be_declined_without_rolling_a_save() -> None:
    """Leave the target unchanged when the attacker declines the optional rule."""

    session = _prepared_session((15,))
    state = session.encounter_state
    assert state is not None
    session._choose(_maul_attack_id(session))

    result = _choose_mastery(session, "decline_weapon_mastery")
    mastery = next(
        event for event in result.events if event.type == "weapon_mastery_resolved"
    )

    assert mastery.data == {
        "mastery": "Topple",
        "weapon_id": "maul",
        "target_ref": "ogre_target",
        "used": False,
    }
    assert not any(
        applied.condition is Condition.PRONE and applied.target_ref == "ogre_target"
        for applied in state.conditions
    )


def test_topple_is_not_offered_after_a_miss() -> None:
    """Require a confirmed Maul hit before opening the mastery decision."""

    session = _prepared_session((1,))
    state = session.encounter_state
    assert state is not None

    result = session._choose(_maul_attack_id(session))

    assert any(
        event.type == "attack_resolved" and event.data["hit"] is False
        for event in result.events
    )
    assert state.current_decision().kind != "weapon_mastery"


def test_topple_follows_savage_attacker_damage_finalization() -> None:
    """Open Topple only after the pending weapon-damage choice is accepted."""

    session = _prepared_session((15, 1), suppress_savage_attacker=False)
    state = session.encounter_state
    assert state is not None

    first = session._choose(_maul_attack_id(session))
    assert any(event.type == "attack_pending" for event in first.events)
    assert state.current_decision().kind == "reroll_dice"

    accepted = session._choose(
        next(
            option.id
            for option in session._read().action_options
            if option.kind == "accept_roll"
        )
    )

    assert any(event.type == "decision_opened" for event in accepted.events)
    assert state.current_decision().kind == "weapon_mastery"
    result = _choose_mastery(session, "use_weapon_mastery")
    assert any(event.type == "weapon_mastery_resolved" for event in result.events)
    assert any(
        applied.condition is Condition.PRONE and applied.target_ref == "ogre_target"
        for applied in state.conditions
    )
