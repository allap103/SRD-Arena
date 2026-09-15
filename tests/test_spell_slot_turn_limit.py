"""Enforce the 2024 one-slot-per-caster-per-turn rule through shared rules."""

from dataclasses import replace

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters.actions.option_discovery.spellcasting import (
    spell_cast_block_reason_for,
    spend_spell_resources,
)
from srd_arena.domain.encounters.encounter_models.actions import ActionCost
from srd_arena.domain.encounters.turn_lifecycle import advance_turn, skip_defeated_turn
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.metadata import SpellCastingTime
from srd_arena.engine.api import AimAction, SelectAction, Session
from tests.encounter_runtime_support import player_first_initiative

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)


def session() -> Session:
    """Start the fixed encounter with the warlock acting first."""
    result = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    result.observe()
    return result


def aim(game: Session, spell_id: str) -> AimAction:
    """Build a legal aim with the current public action and decision identifiers."""
    observation = game.observe()
    assert observation.encounter is not None
    action = next(
        a
        for a in observation.scene.action_details
        if a.source_id == spell_id
        and a.resource_level == (3 if spell_id == "misty_step" else None)
    )
    return AimAction(action.id, 5.5, 3.5, observation.encounter.decision.id)


@pytest.mark.parametrize(
    "first,second",
    [
        ("stinking_cloud", "misty_step"),
        ("misty_step", "stinking_cloud"),
        ("hypnotic_pattern", "misty_step"),
        ("misty_step", "hypnotic_pattern"),
    ],
)
def test_second_slot_cast_is_disabled_and_cannot_be_forced(
    first: str, second: str
) -> None:
    game = session()
    assert game.execute(aim(game, first)).accepted
    state = game.encounter_state
    assert state is not None
    warlock = state.creatures["warlock"]
    casting = warlock.creature.spellcasting
    assert casting is not None
    assert casting.spell_slots_remaining == {3: 1}
    assert state.turn.spell_slot_users == {"warlock"}
    observation = game.observe()
    command = aim(game, second)
    second_action = next(
        a for a in observation.scene.action_details if a.id == command.action_id
    )
    assert not second_action.enabled
    before = (
        warlock.position,
        warlock.actions_remaining,
        warlock.bonus_action_available,
    )
    result = game.execute(command)
    assert not result.accepted or (
        result.update is not None
        and any(
            e.type == "action_resolved" and e.data.get("success") is False
            for e in result.update.events
        )
    )
    assert casting.spell_slots_remaining == {3: 1}
    assert before == (
        warlock.position,
        warlock.actions_remaining,
        warlock.bonus_action_available,
    )


@pytest.mark.parametrize("free_first", [False, True])
@pytest.mark.parametrize("spell_id", ["false_life", "mind_sliver"])
def test_slot_free_feature_and_cantrip_can_share_turn_with_misty_step(
    free_first: bool,
    spell_id: str,
) -> None:
    game = session()

    def cast_free() -> None:
        observation = game.observe()
        assert observation.encounter is not None
        action = next(
            a
            for a in observation.scene.action_details
            if a.source_id == spell_id and a.enabled
        )
        result = game.execute(
            SelectAction(action.id, observation.encounter.decision.id)
        )
        assert result.accepted and result.update is not None
        assert any(e.type == "spell_cast" for e in result.update.events)

    if free_first:
        cast_free()
    assert game.execute(aim(game, "misty_step")).accepted
    if not free_first:
        cast_free()
    state = game.encounter_state
    assert state is not None
    casting = state.creatures["warlock"].creature.spellcasting
    assert casting is not None and casting.spell_slots_remaining == {3: 1}
    assert state.turn.spell_slot_users == {"warlock"}


def test_invalid_destination_does_not_use_turn_slot_allowance() -> None:
    game = session()
    command = replace(aim(game, "misty_step"), x=11.5, y=8.5)
    game.execute(command)
    assert game.encounter_state is not None
    assert game.encounter_state.turn.spell_slot_users == set()
    result = game.execute(aim(game, "misty_step"))
    assert result.accepted
    assert game.encounter_state.turn.spell_slot_users == {"warlock"}


def test_slot_allowance_is_per_caster_and_resets_on_other_creatures_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = session()
    game.execute(aim(game, "misty_step"))
    state = game.encounter_state
    assert state is not None
    casting = state.creatures["warlock"].creature.spellcasting
    assert casting is not None
    reaction = Spell(
        "shield", "Shield", "XPHB", 1, casting_times=(SpellCastingTime(1, "reaction"),)
    )
    assert "this turn" in str(
        spell_cast_block_reason_for(state, casting, reaction, ActionCost(reaction=1), 3)
    )
    original = state.current_decision()
    with monkeypatch.context() as patch:
        patch.setattr(
            type(state),
            "current_decision",
            lambda self: replace(original, creature_ref="barbarian"),
        )
        assert (
            spell_cast_block_reason_for(
                state, casting, reaction, ActionCost(reaction=1), 3
            )
            is None
        )
    advance_turn(state)
    assert state.turn.spell_slot_users == set()
    # A reaction uses its caster's allowance on this new turn, even though
    # initiative belongs to someone else. Selecting a reactor must not reset it.
    with monkeypatch.context() as patch:
        patch.setattr(type(state), "current_decision", lambda self: original)
        assert (
            spell_cast_block_reason_for(
                state, casting, reaction, ActionCost(reaction=1), 3
            )
            is None
        )
        spend_spell_resources(state, casting, reaction, ActionCost(reaction=1), 3)
        assert state.turn.spell_slot_users == {"warlock"}
    skip_defeated_turn(state)
    assert state.turn.spell_slot_users == set()
    game.reset(seed=42)
    assert game.encounter_state is not None
    assert game.encounter_state.turn.spell_slot_users == set()
