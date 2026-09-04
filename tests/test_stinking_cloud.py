"""Verify Stinking Cloud placement and its reusable turn-start area lifecycle."""

from dataclasses import replace
from pathlib import Path

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects import ActionProhibition, Condition, OngoingEffect
from srd_arena.domain.encounters.actions.eligibility_rules.spell_targeting import (
    spell_target_eligibility,
)
from srd_arena.domain.encounters.effect_lifecycle.area_turn_start import (
    resolve_turn_start_area_effects,
)
from srd_arena.domain.encounters.effect_lifecycle.concentration import (
    end_concentration,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_end import (
    expire_ongoing_effects_for_turn_end,
)
from srd_arena.domain.encounters.encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.rule_queries.obstructions import cover_between
from srd_arena.domain.encounters.rule_queries.visibility import (
    creature_can_see_creature,
)
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.encounters.turn_lifecycle import expire_conditions_for_turn_end
from srd_arena.engine.commands import AimAction, CommandResult
from srd_arena.engine.observation_models import ActionObservation
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    as_mapping,
    player_first_initiative,
    use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session(*, roll: int = 1) -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session.observe()
    use_deterministic_dice(session, die_roller=lambda _sides: roll)
    return session


def _spell_action(session: Session) -> ActionObservation:
    return next(
        action
        for action in session.observe().scene.action_details
        if action.source_id == "stinking_cloud" and action.enabled
    )


def _cast_cloud(session: Session) -> CommandResult:
    observation = session.observe()
    assert observation.encounter is not None
    return session.execute(
        AimAction(
            _spell_action(session).id,
            8.5,
            4.5,
            observation.encounter.decision.id,
        )
    )


def _cloud_effect(session: Session) -> OngoingEffect:
    assert session.encounter_state is not None
    return next(
        effect
        for effect in session.encounter_state.ongoing_effects
        if effect.identity.source.definition_id == "stinking_cloud"
    )


def test_cast_creates_observable_area_without_affecting_initial_occupants() -> None:
    session = _session()

    result = _cast_cloud(session)

    assert result.accepted
    effect = _cloud_effect(session)
    assert effect.area is not None
    assert effect.area.shape == "radius"
    assert effect.target_refs == ()
    assert effect.obscures_vision is True
    assert session.encounter_state is not None
    assert not session.encounter_state.has_condition("goblin_1", Condition.POISONED)
    observation = session.observe()
    assert observation.encounter is not None
    observed = next(
        candidate
        for candidate in observation.encounter.ongoing_effects
        if candidate.definition_id == "stinking_cloud"
    )
    assert observed.area is not None
    assert observed.area["shape"] == "radius"
    assert observed.obscures_vision is True


def test_cloud_blocks_sight_without_blocking_line_of_effect() -> None:
    session = _session()
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    warlock = state.creatures["warlock"].creature
    assert warlock.spellcasting is not None
    hold_person = next(
        spell
        for spell in warlock.spellcasting.learned_spells
        if spell.id == "hold_person"
    )

    assert not creature_can_see_creature(state, "warlock", "goblin_1")
    assert not creature_can_see_creature(state, "goblin_1", "warlock")
    assert cover_between(state, "warlock", "goblin_1").has_line_of_effect
    eligibility = spell_target_eligibility(
        state,
        "warlock",
        "goblin_1",
        hold_person,
    )
    assert "target_not_visible" in {failure.code for failure in eligibility.failures}


def test_mutual_obscuration_cancels_attack_modes_but_blindsight_breaks_the_tie() -> (
    None
):
    session = _session()
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    warlock_position = state.creatures["warlock"].position

    assert (
        attack_roll_mode_for(
            state,
            "warlock",
            "goblin_1",
            "ranged",
            warlock_position,
            (),
        )
        == "normal"
    )
    goblin = state.creatures["goblin_1"].creature
    goblin.statistics = replace(
        goblin.statistics,
        senses=("Blindsight 60 ft.",),
    )
    assert creature_can_see_creature(state, "goblin_1", "warlock")
    assert (
        attack_roll_mode_for(
            state,
            "warlock",
            "goblin_1",
            "ranged",
            warlock_position,
            (),
        )
        == "disadvantage"
    )


def test_failed_turn_start_save_poisons_and_prohibits_actions_for_that_turn() -> None:
    session = _session(roll=1)
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("goblin_1")
    state.interrupts.decision_stack.clear()
    progress = EncounterProgress()

    resolve_turn_start_area_effects(state, "goblin_1", progress)

    assert state.has_condition("goblin_1", Condition.POISONED)
    child = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.parent_id == _cloud_effect(session).identity.id
    )
    assert any(isinstance(rule, ActionProhibition) for rule in child.rule_effects)
    action = EncounterAction(
        "Attack",
        "attack",
        creature_ref="goblin_1",
        cost=ActionCost(action=1),
    )
    bonus_action = EncounterAction(
        "Dash",
        "dash",
        creature_ref="goblin_1",
        cost=ActionCost(bonus_action=1),
    )
    move = EncounterAction("Move", "move", "left", creature_ref="goblin_1")
    assert "effect.action_prohibited" in {
        failure.code for failure in state.action_eligibility(action).failures
    }
    assert "effect.action_prohibited" in {
        failure.code for failure in state.action_eligibility(bonus_action).failures
    }
    assert "effect.action_prohibited" not in {
        failure.code for failure in state.action_eligibility(move).failures
    }
    assert progress.events[-1].type == "ongoing_area_effect_resolved"
    assert as_mapping(progress.events[-1].data["save_detail"])["success"] is False


def test_successful_turn_start_save_creates_no_target_state() -> None:
    session = _session(roll=20)
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state

    resolve_turn_start_area_effects(state, "goblin_1", EncounterProgress())

    assert not state.has_condition("goblin_1", Condition.POISONED)
    assert all(effect.identity.parent_id is None for effect in state.ongoing_effects)


def test_turn_end_removes_cloud_failure_but_not_the_cloud() -> None:
    session = _session(roll=1)
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    parent_id = _cloud_effect(session).identity.id
    resolve_turn_start_area_effects(state, "goblin_1")

    expire_ongoing_effects_for_turn_end(state, "goblin_1")
    expire_conditions_for_turn_end(state, "goblin_1")

    assert not state.has_condition("goblin_1", Condition.POISONED)
    assert any(effect.identity.id == parent_id for effect in state.ongoing_effects)
    assert all(effect.identity.parent_id is None for effect in state.ongoing_effects)


def test_ending_concentration_removes_area_and_current_turn_child_state() -> None:
    session = _session(roll=1)
    _cast_cloud(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    resolve_turn_start_area_effects(state, "goblin_1")

    end_concentration(state, "warlock")

    assert not any(
        effect.identity.source.definition_id == "stinking_cloud"
        for effect in state.ongoing_effects
    )
    assert not state.has_condition("goblin_1", Condition.POISONED)
