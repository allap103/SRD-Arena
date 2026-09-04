"""Verify Command authoring and delayed state through the public session path."""

from itertools import pairwise
from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import CompelledTurnEffect, capability_effects
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.rule_effects import CompelledTurn
from srd_arena.domain.effects.runtime import UntilTurnEnd
from srd_arena.domain.encounters.creature_control import (
    available_creature_actions,
    creature_action_candidates,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_end import (
    expire_ongoing_effects_for_turn_end,
)
from srd_arena.domain.encounters.rule_queries.compulsions import active_compelled_turn
from srd_arena.domain.encounters.spatial import creature_distance
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


def _session(*, save_roll: int) -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("warlock")
    state.interrupts.decision_stack.clear()
    use_deterministic_dice(session, die_roller=lambda _sides: save_roll)
    return session


def _command_option(
    session: Session,
    *,
    target_ref: str,
    instruction: str,
) -> ActionOption:
    return next(
        option
        for option in session._read().action_options
        if option.enabled
        and option.kind == "spell"
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "command"
        and option.details.target_ref == target_ref
        and option.details.selected_option == instruction
    )


def _cast_command(
    session: Session,
    *,
    target_ref: str,
    instruction: str,
) -> None:
    session._choose(
        _command_option(
            session,
            target_ref=target_ref,
            instruction=instruction,
        ).id
    )
    confirm = next(
        option
        for option in session._read().action_options
        if option.enabled and option.kind == "confirm_spell_targets"
    )
    session._choose(confirm.id)


def test_command_translates_closed_options_next_turn_duration_and_upcasting() -> None:
    spell = build_spell(load_spell_catalog(SYSTEM_CONTENT_ROOT).find("Command", "XPHB"))

    assert spell.definition is not None
    compelled = next(
        effect
        for effect in capability_effects(spell.definition)
        if isinstance(effect, CompelledTurnEffect)
    )
    assert compelled.options == ("approach", "drop", "flee", "grovel", "halt")
    assert (compelled.duration.kind, compelled.duration.creature) == (
        "next_turn_end",
        "target",
    )
    assert spell.definition.scaling[0].per_level[0].kind == "target_count"
    assert spell.definition.scaling[0].per_level[0].amount == 1


def test_command_advertises_each_predefined_instruction_as_typed_option() -> None:
    session = _session(save_roll=1)

    options = {
        option.details.selected_option
        for option in session._read().action_options
        if option.enabled
        and isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "command"
        and option.details.target_ref == "goblin_1"
    }

    assert options == {"approach", "drop", "flee", "grovel", "halt"}


def test_failed_command_save_creates_source_aware_next_turn_instruction() -> None:
    session = _session(save_roll=1)

    _cast_command(session, target_ref="goblin_1", instruction="halt")

    assert session.encounter_state is not None
    state = session.encounter_state
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "command"
    )
    assert effect.identity.source.applied_by_ref == "warlock"
    assert effect.target_refs == ("goblin_1",)
    assert effect.duration == UntilTurnEnd("goblin_1")
    assert effect.rule_effects == (CompelledTurn("halt"),)

    expire_ongoing_effects_for_turn_end(state, "barbarian")
    assert effect in state.ongoing_effects
    expire_ongoing_effects_for_turn_end(state, "goblin_1")
    assert effect not in state.ongoing_effects


def test_successful_command_save_creates_no_instruction() -> None:
    session = _session(save_roll=20)

    _cast_command(session, target_ref="goblin_1", instruction="grovel")

    assert session.encounter_state is not None
    assert not any(
        effect.identity.source.definition_id == "command"
        for effect in session.encounter_state.ongoing_effects
    )


def _make_target_current(session: Session, target_ref: str) -> None:
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index(target_ref)
    state.interrupts.decision_stack.clear()


def test_halt_replaces_scripted_action_menu_and_ends_the_commanded_turn() -> None:
    session = _session(save_roll=1)
    _cast_command(session, target_ref="goblin_1", instruction="halt")
    _make_target_current(session, "goblin_1")

    assert session.encounter_state is not None
    state = session.encounter_state
    candidates = creature_action_candidates(state, "goblin_1")
    compelled = next(
        action for action in candidates if action.kind == "obey_compelled_turn"
    )
    normal_wait = next(action for action in candidates if action.kind == "wait")

    assert state.action_eligibility(compelled).allowed
    assert state.action_eligibility(normal_wait).failures[0].code == "compelled_turn"

    update = session.advance_one_automatic_action()

    assert any(
        event.type == "compelled_turn_resolved" and event.data["instruction"] == "halt"
        for event in update.events
    )
    assert active_compelled_turn(state, "goblin_1") is None


def test_grovel_applies_persistent_sourced_prone_and_ends_the_commanded_turn() -> None:
    session = _session(save_roll=1)
    _cast_command(session, target_ref="goblin_1", instruction="grovel")
    _make_target_current(session, "goblin_1")

    update = session.advance_one_automatic_action()

    assert session.encounter_state is not None
    state = session.encounter_state
    prone = next(
        applied
        for applied in state.conditions_for("goblin_1")
        if applied.condition is Condition.PRONE
    )
    assert prone.source_ref == "warlock"
    assert prone.identity.source.definition_id == "command"
    assert active_compelled_turn(state, "goblin_1") is None
    assert any(
        event.type == "compelled_turn_resolved"
        and event.data["instruction"] == "grovel"
        for event in update.events
    )


@pytest.mark.parametrize("instruction", ["approach", "flee"])
def test_movement_instruction_constrains_each_step_and_completes_turn(
    instruction: str,
) -> None:
    session = _session(save_roll=1)
    _cast_command(session, target_ref="goblin_1", instruction=instruction)
    _make_target_current(session, "goblin_1")

    assert session.encounter_state is not None
    state = session.encounter_state
    distances = [int(creature_distance(state, "goblin_1", "warlock"))]
    initially_available = available_creature_actions(state, "goblin_1")
    assert initially_available
    assert {action.kind for action in initially_available} == {"move"}
    assert all(
        not state.action_eligibility(action).allowed
        for action in creature_action_candidates(state, "goblin_1")
        if action.kind in {"attack", "wait"}
    )

    completion_seen = False
    for _ in range(10):
        if state.current_decision().creature_ref != "goblin_1":
            break
        update = session.advance_one_automatic_action()
        if any(event.type == "movement_resolved" for event in update.events):
            distances.append(int(creature_distance(state, "goblin_1", "warlock")))
        completion_seen = completion_seen or any(
            event.type == "compelled_turn_resolved"
            and event.data["instruction"] == instruction
            for event in update.events
        )

    assert state.current_decision().creature_ref != "goblin_1"
    assert completion_seen
    assert active_compelled_turn(state, "goblin_1") is None
    assert len(distances) > 1
    if instruction == "approach":
        assert all(after < before for before, after in pairwise(distances))
        assert distances[-1] <= 1
    else:
        assert all(after > before for before, after in pairwise(distances))
