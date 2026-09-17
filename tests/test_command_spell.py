"""Verify Command authoring and delayed state through the public session path."""

from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import CompelledTurnEffect, capability_effects
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.application import condition_from_effect
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.rule_effects import CompelledTurn
from srd_arena.domain.effects.runtime import UntilTurnEnd
from srd_arena.domain.encounters import TerrainCell, TerrainTraversal
from srd_arena.domain.encounters.creature_control import (
    available_creature_actions,
    creature_action_candidates,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_end import (
    expire_ongoing_effects_for_turn_end,
)
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.encounters.rule_queries.compulsions import active_compelled_turn
from srd_arena.domain.encounters.spatial import creature_distance
from srd_arena.domain.geometry import Position
from srd_arena.engine.queries import ActionOption, SpellOptionDetails
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    player_first_initiative,
    submit_complete_spell,
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
    option = _command_option(session, target_ref=target_ref, instruction=instruction)
    submit_complete_spell(session, option.id, (target_ref,))


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
        option.details.selected_option: option
        for option in session._read().action_options
        if isinstance(option.details, SpellOptionDetails)
        and option.details.source_id == "command"
        and option.details.target_ref == "goblin_1"
    }

    assert set(options) == {"approach", "drop", "flee", "grovel", "halt"}
    assert options["drop"].availability == "unimplemented"
    assert options["drop"].eligibility.failures[0].code == (
        "unsupported_compelled_turn_option"
    )
    assert all(
        option.availability == "available"
        for instruction, option in options.items()
        if instruction != "drop"
    )


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
        and event.data["condition_applied"] is True
        for event in update.events
    )


def test_grovel_still_ends_the_turn_when_the_target_is_immune_to_prone() -> None:
    session = _session(save_roll=1)
    assert session.encounter_state is not None
    state = session.encounter_state
    target = state.creatures["goblin_1"].creature
    target.statistics = replace(
        target.statistics,
        condition_immunities=frozenset({Condition.PRONE}),
    )
    _cast_command(session, target_ref="goblin_1", instruction="grovel")
    _make_target_current(session, "goblin_1")

    update = session.advance_one_automatic_action()

    assert state.current_decision().creature_ref != "goblin_1"
    assert not state.has_condition("goblin_1", Condition.PRONE)
    assert any(
        event.type == "compelled_turn_resolved"
        and event.data["instruction"] == "grovel"
        and event.data["condition_applied"] is False
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
        assert all(after >= before for before, after in pairwise(distances))
        assert distances[-1] > distances[0]


def test_approach_uses_a_shortest_route_around_blocked_terrain() -> None:
    session = _session(save_roll=1)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["warlock"].position = Position(1, 2)
    state.creatures["goblin_1"].position = Position(5, 2)
    state.creatures["barbarian"].position = Position(10, 8)
    state.definition.terrain = tuple(
        TerrainCell(Position(4, y), traversal=TerrainTraversal.BLOCKED)
        for y in (1, 2, 3)
    )
    _cast_command(session, target_ref="goblin_1", instruction="approach")
    _make_target_current(session, "goblin_1")

    available = available_creature_actions(state, "goblin_1")

    assert {action.value for action in available} == {"up", "down"}
    completion = next(
        action
        for action in creature_action_candidates(state, "goblin_1")
        if action.kind == "obey_compelled_turn"
    )
    assert not state.action_eligibility(completion).allowed


def test_flee_can_move_laterally_toward_a_farther_reachable_position() -> None:
    session = _session(save_roll=1)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["warlock"].position = Position(4, 4)
    state.creatures["goblin_1"].position = Position(6, 4)
    state.creatures["barbarian"].position = Position(0, 8)
    state.definition.terrain = tuple(
        TerrainCell(Position(7, y), traversal=TerrainTraversal.BLOCKED)
        for y in (3, 4, 5)
    )
    _cast_command(session, target_ref="goblin_1", instruction="flee")
    _make_target_current(session, "goblin_1")
    initial_distance = creature_distance(state, "goblin_1", "warlock")

    available = available_creature_actions(state, "goblin_1")

    assert {action.value for action in available} == {"up", "down"}
    update = session.advance_one_automatic_action()
    assert any(event.type == "movement_resolved" for event in update.events)
    assert creature_distance(state, "goblin_1", "warlock") == initial_distance


def test_flee_routes_with_a_grappled_creatures_footprint() -> None:
    session = _session(save_roll=1)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["warlock"].position = Position(3, 4)
    state.creatures["goblin_1"].position = Position(5, 4)
    state.creatures["barbarian"].position = Position(5, 5)
    state.creatures["goblin_2"].position = Position(10, 8)
    state.creatures["goblin_3"].position = Position(10, 7)
    state.definition.terrain = (
        TerrainCell(Position(6, 5), traversal=TerrainTraversal.BLOCKED),
    )
    assert apply_grapple(
        state,
        condition_from_effect(
            EffectResult(
                kind="apply_condition",
                target_ref="barbarian",
                data={
                    "condition": "grappled",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ),
    ).accepted
    _cast_command(session, target_ref="goblin_1", instruction="flee")
    _make_target_current(session, "goblin_1")

    available = available_creature_actions(state, "goblin_1")

    assert available
    assert {action.kind for action in available} == {"move"}
    assert all(action.value != "right" for action in available)
