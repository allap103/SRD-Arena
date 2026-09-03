"""Verify Mind Sliver through the canonical Warlock session boundary."""

from pathlib import Path

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.runtime import UntilTurnEnd
from srd_arena.domain.encounters.effect_lifecycle.turn_end import (
    expire_ongoing_effects_for_turn_end,
)
from srd_arena.engine.queries import ActionOption, SpellOptionDetails
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    player_first_initiative,
    use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session() -> Session:
    session = Session(load_encounter_directory(str(WARLOCK_TRAINING_ENCOUNTER_DIR)))
    session.read()
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 1 if sides == 20 else 3,
    )
    return session


def _is_spell_option(
    option: ActionOption,
    spell_id: str,
    target_ref: str,
) -> bool:
    return (
        option.kind == "spell"
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == spell_id
        and option.details.target_ref == target_ref
    )


def _cast_mind_sliver(session: Session) -> None:
    action = next(
        action
        for action in session.read().action_options
        if _is_spell_option(action, "mind_sliver", "goblin_1")
    )
    result = session.choose(action.id)
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    damage = spell_event.data["damage_roll_details"]
    assert isinstance(damage, list)
    assert damage[0]["dice"] == "2d6"
    assert damage[0]["total"] == 6


def test_mind_sliver_penalty_is_consumed_by_the_targets_next_save() -> None:
    session = _session()
    _cast_mind_sliver(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    mind_sliver = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "mind_sliver"
    )
    assert isinstance(mind_sliver.duration, UntilTurnEnd)
    assert mind_sliver.duration.creature_ref == "warlock"
    assert mind_sliver.duration.round_number == 2

    warlock = state.creatures["warlock"]
    warlock.actions_remaining = 1
    warlock.action_used_this_turn = False
    warlock.magic_actions_remaining = 1
    action = next(
        action
        for action in session.read().action_options
        if action.enabled and _is_spell_option(action, "hideous_laughter", "goblin_1")
    )
    opened = session.choose(action.id)
    assert [event.type for event in opened.events] == ["action_declared"]
    confirm = next(
        option
        for option in session.read().action_options
        if option.kind == "confirm_spell_targets"
    )
    result = session.choose(confirm.id)

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    save = spell_event.data["save_detail"]
    assert isinstance(save, dict)
    assert save["ability"] == "wisdom"
    assert save["modifier"] == -4
    assert save["success"] is False
    assert not any(
        effect.identity.source.definition_id == "mind_sliver"
        for effect in state.ongoing_effects
    )


def test_unused_mind_sliver_penalty_expires_at_source_next_turn_end() -> None:
    session = _session()
    _cast_mind_sliver(session)
    assert session.encounter_state is not None
    state = session.encounter_state

    expire_ongoing_effects_for_turn_end(state, "warlock")
    assert any(
        effect.identity.source.definition_id == "mind_sliver"
        for effect in state.ongoing_effects
    )

    state.round.number = 2
    expire_ongoing_effects_for_turn_end(state, "warlock")
    assert not any(
        effect.identity.source.definition_id == "mind_sliver"
        for effect in state.ongoing_effects
    )
