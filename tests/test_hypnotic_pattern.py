"""Verify Hypnotic Pattern through authored content and public engine decisions."""

from dataclasses import replace
from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import build_spell, load_spell_catalog
from srd_arena.domain.capabilities import (
    ConditionEffect,
    ConditionImmunityRequirement,
    ConditionRequirement,
    SpeedMultiplierEffect,
    primary_effects,
)
from srd_arena.domain.capabilities.resolutions import SavingThrowResolution
from srd_arena.domain.effects import SpeedMultiplier
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.actions.creature_actions.special import (
    special_action_candidates,
)
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.effect_lifecycle.lifecycle_events import (
    resolve_effect_lifecycle_event,
)
from srd_arena.domain.encounters.rule_queries.numeric import effective_speed
from srd_arena.engine.commands import AimAction, CommandResult, SelectAction
from srd_arena.engine.observation_models import ActionObservation
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    as_mapping,
    as_sequence,
    player_first_initiative,
    use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _session() -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session.observe()
    use_deterministic_dice(session, die_roller=lambda _sides: 1)
    return session


def _hypnotic_pattern_action(session: Session) -> ActionObservation:
    return next(
        action
        for action in session.observe().scene.action_details
        if action.source_id == "hypnotic_pattern" and action.enabled
    )


def _cast_hypnotic_pattern(session: Session) -> CommandResult:
    observation = session.observe()
    assert observation.encounter is not None
    action = _hypnotic_pattern_action(session)
    return session.execute(
        AimAction(
            action.id,
            8.5,
            4.5,
            observation.encounter.decision.id,
        )
    )


def test_hypnotic_pattern_authors_shared_conditions_speed_and_end_events() -> None:
    spell = build_spell(
        load_spell_catalog(SYSTEM_CONTENT_ROOT).find("Hypnotic Pattern", "XPHB")
    )

    assert spell.definition is not None
    assert isinstance(spell.definition.resolution, SavingThrowResolution)
    effects = primary_effects(spell.definition)
    assert tuple(
        effect.condition for effect in effects if isinstance(effect, ConditionEffect)
    ) == ("charmed", "incapacitated")
    assert (
        next(
            effect for effect in effects if isinstance(effect, SpeedMultiplierEffect)
        ).numerator
        == 0
    )
    automatic_success = spell.definition.resolution.automatic_success
    assert ConditionImmunityRequirement("charmed") in automatic_success
    assert ConditionRequirement(("blinded",)) in automatic_success
    assert {trigger.event for trigger in spell.definition.triggers} == {
        "target_damaged",
        "adjacent_creature_wakes_target",
    }


def test_failed_hypnotic_pattern_saves_apply_linked_stupor_and_speed_zero() -> None:
    session = _session()

    result = _cast_hypnotic_pattern(session)

    assert result.accepted
    assert session.encounter_state is not None
    state = session.encounter_state
    for target_ref in ("goblin_1", "goblin_2", "goblin_3", "ogre_target"):
        assert state.has_condition(target_ref, Condition.CHARMED)
        assert state.has_condition(target_ref, Condition.INCAPACITATED)
        assert effective_speed(state, target_ref).value == 0
    effect = next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "hypnotic_pattern"
    )
    assert effect.target_refs == (
        "goblin_1",
        "goblin_2",
        "goblin_3",
        "ogre_target",
    )
    assert effect.rule_effects == (SpeedMultiplier(0, 1),)


def test_blinded_and_charmed_immune_creatures_are_not_affected() -> None:
    session = _session()
    assert session.encounter_state is not None
    state = session.encounter_state
    assert apply_condition(
        state,
        build_applied_condition(
            condition=Condition.BLINDED,
            source_ref="barbarian",
            source_label="Barbarian",
            target_ref="goblin_1",
        ),
    ).accepted
    goblin_two = state.creatures["goblin_2"].creature
    goblin_two.statistics = replace(
        goblin_two.statistics,
        condition_immunities=frozenset({Condition.CHARMED}),
    )

    result = _cast_hypnotic_pattern(session)

    assert result.update is not None
    assert not state.has_condition("goblin_1", Condition.CHARMED)
    assert not state.has_condition("goblin_2", Condition.INCAPACITATED)
    cast = next(event for event in result.update.events if event.type == "spell_cast")
    saves = tuple(as_mapping(item) for item in as_sequence(cast.data["save_details"]))
    automatic = {
        str(save["target_ref"]): tuple(
            str(reason) for reason in as_sequence(save["automatic_success_reasons"])
        )
        for save in saves
        if save["automatic_success_reasons"]
    }
    assert automatic["goblin_1"] == ("Hypnotic Pattern: blinded",)
    assert automatic["goblin_2"] == ("Hypnotic Pattern: immune to charmed",)


def test_damage_ends_hypnotic_pattern_only_for_the_damaged_target() -> None:
    session = _session()
    _cast_hypnotic_pattern(session)
    assert session.encounter_state is not None
    state = session.encounter_state

    resolve_effect_lifecycle_event(
        state,
        "target_damaged",
        actor_ref="barbarian",
        target_ref="goblin_1",
    )

    assert not state.has_condition("goblin_1", Condition.CHARMED)
    assert effective_speed(state, "goblin_1").value > 0
    assert state.has_condition("goblin_2", Condition.CHARMED)
    assert effective_speed(state, "goblin_2").value == 0


def test_adjacent_creature_can_spend_an_action_to_rouse_a_pattern_target() -> None:
    session = _session()
    _cast_hypnotic_pattern(session)
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["warlock"].position.x = 7
    state.creatures["warlock"].position.y = 2
    state.creatures["warlock"].actions_remaining = 1
    state.interrupts.decision_stack.clear()

    candidate = next(
        action
        for action in special_action_candidates(state, "warlock")
        if action.kind == "rouse_spell_target" and action.value == "goblin_1"
    )
    observation = session.observe()
    assert observation.encounter is not None
    public_action = next(
        action
        for action in observation.scene.action_details
        if action.id == candidate.id and action.enabled
    )
    result = session.execute(
        SelectAction(public_action.id, observation.encounter.decision.id)
    )

    assert result.accepted
    assert not state.has_condition("goblin_1", Condition.CHARMED)
    assert state.has_condition("goblin_2", Condition.CHARMED)
    assert state.creatures["warlock"].actions_remaining == 0
