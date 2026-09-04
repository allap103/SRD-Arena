"""Behavioral coverage for the source-aware Charmed condition slice."""

from pathlib import Path

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.capabilities import CapabilityTarget, OutcomeStage
from srd_arena.domain.creatures import SavingThrowActionDefinition
from srd_arena.domain.effects import (
    ConditionSuppression,
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    RuntimeStateIdentity,
)
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.reaction_runtime.opportunity_execution import (
    apply_reaction_action,
)
from srd_arena.domain.encounters.rule_queries.permissions import (
    TargetingKind,
    target_eligibility,
)
from srd_arena.engine.api import AimAction, SelectAction
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import choose_advertised_action

ENCOUNTERS_ROOT = Path(__file__).parents[1] / "content" / "encounters"
WARLOCK_TRAINING_ENCOUNTER_DIR = ENCOUNTERS_ROOT / "warlock_training"
FULL_CONTROL_ENCOUNTER_DIR = ENCOUNTERS_ROOT / "archive" / "full_control_showcase"
STAT_BLOCK_ENCOUNTER_DIR = ENCOUNTERS_ROOT / "archive" / "stat_block_action_showcase"


def _warlock_session() -> Session:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("warlock")
    warlock = state.creatures["warlock"]
    warlock.position.x, warlock.position.y = 4, 4
    state.creatures["goblin_1"].position.x = 5
    state.creatures["goblin_1"].position.y = 4
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 5
    state.creatures["goblin_3"].position.x = 9
    state.creatures["goblin_3"].position.y = 7
    state.creatures["barbarian"].position.x = 1
    state.creatures["barbarian"].position.y = 7
    return session


def _charm(
    session: Session,
    *,
    creature_ref: str,
    source_ref: str,
    origin_id: str | None = None,
) -> str:
    state = session.encounter_state
    assert state is not None
    applied = build_applied_condition(
        condition=Condition.CHARMED,
        source_ref=source_ref,
        source_label=state.creatures[source_ref].creature.name,
        target_ref=creature_ref,
        origin_id=origin_id,
    )
    assert apply_condition(state, applied).accepted
    return applied.id


def test_charmed_prohibits_only_the_source_of_each_effective_application() -> None:
    session = _warlock_session()
    state = session.encounter_state
    assert state is not None
    provider_id = _charm(
        session,
        creature_ref="warlock",
        source_ref="goblin_1",
    )

    charmer = target_eligibility(
        state,
        "warlock",
        "goblin_1",
        TargetingKind.ATTACK,
    )
    other_enemy = target_eligibility(
        state,
        "warlock",
        "goblin_2",
        TargetingKind.ATTACK,
    )

    assert charmer.allowed is False
    assert charmer.failures[0].code == "condition.charmed_target_prohibited"
    assert charmer.failures[0].state_ids == (provider_id,)
    assert other_enemy.allowed is True

    other_provider_id = _charm(
        session,
        creature_ref="warlock",
        source_ref="goblin_2",
        origin_id="second_charm",
    )
    second_charmer = target_eligibility(
        state,
        "warlock",
        "goblin_2",
        TargetingKind.DAMAGING_MAGICAL_EFFECT,
    )

    assert second_charmer.allowed is False
    assert second_charmer.failures[0].state_ids == (other_provider_id,)


def test_charmed_blocks_attacks_and_damaging_spells_but_not_other_magic() -> None:
    session = _warlock_session()
    _charm(session, creature_ref="warlock", source_ref="goblin_1")

    actions = session.observe().scene.action_details
    attack_charmer = next(
        action
        for action in actions
        if action.kind == "attack" and action.target_ref == "goblin_1"
    )
    attack_other = next(
        action
        for action in actions
        if action.kind == "attack" and action.target_ref == "goblin_2"
    )
    blast_charmer = next(
        action
        for action in actions
        if action.kind == "spell"
        and action.source_id == "eldritch_blast"
        and action.target_ref == "goblin_1"
        and "condition.charmed_target_prohibited"
        in {reason.code for reason in action.reasons}
    )
    blast_other = next(
        action
        for action in actions
        if action.kind == "spell"
        and action.source_id == "eldritch_blast"
        and action.target_ref == "goblin_2"
        and action.enabled
    )
    laughter_charmer = next(
        action
        for action in actions
        if action.kind == "spell"
        and action.source_id == "hideous_laughter"
        and action.target_ref == "goblin_1"
        and action.enabled
    )

    for blocked in (attack_charmer, blast_charmer):
        assert blocked.enabled is False
        assert "condition.charmed_target_prohibited" in {
            reason.code for reason in blocked.reasons
        }
    assert attack_other.enabled is True
    assert blast_other.enabled is True
    assert laughter_charmer.enabled is True


def test_charmed_allows_a_non_damaging_stat_block_ability() -> None:
    session = _warlock_session()
    state = session.encounter_state
    assert state is not None
    state.creatures["warlock"].creature.stat_block_actions["Distract"] = (
        SavingThrowActionDefinition(
            "Distract",
            CapabilityTarget("creature", range_feet=30),
            "wis",
            10,
            (OutcomeStage(()),),
            (),
            "none",
            (),
        )
    )
    _charm(session, creature_ref="warlock", source_ref="goblin_1")

    action = next(
        action
        for action in session.observe().scene.action_details
        if action.kind == "stat_block"
        and action.source_id == "Distract"
        and action.target_ref == "goblin_1"
    )

    assert action.enabled is True


def test_suppressing_charmed_temporarily_restores_targeting_permission() -> None:
    session = _warlock_session()
    state = session.encounter_state
    assert state is not None
    _charm(session, creature_ref="warlock", source_ref="goblin_1")
    suppression = OngoingEffect(
        identity=RuntimeStateIdentity(
            id="effect:charmed-suppression",
            source=EffectSource(
                kind=EffectSourceKind.SPELL,
                definition_id="test_suppression",
                applied_by_ref="warlock",
            ),
        ),
        target_refs=("warlock",),
        rule_effects=(ConditionSuppression(frozenset({Condition.CHARMED})),),
    )
    state.ongoing_effects.append(suppression)

    while_suppressed = target_eligibility(
        state,
        "warlock",
        "goblin_1",
        TargetingKind.ATTACK,
    )
    state.ongoing_effects.remove(suppression)
    after_suppression = target_eligibility(
        state,
        "warlock",
        "goblin_1",
        TargetingKind.ATTACK,
    )

    assert while_suppressed.allowed is True
    assert after_suppression.allowed is False
    assert after_suppression.failures[0].code == ("condition.charmed_target_prohibited")


def test_charmed_rejects_an_area_spell_aimed_over_the_charmer() -> None:
    session = _warlock_session()
    _charm(session, creature_ref="warlock", source_ref="goblin_1")
    observation = session.observe()
    assert observation.encounter is not None
    fireball = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.source_id == "fireball" and action.enabled
    )
    charmer = observation.encounter.creature("goblin_1")

    result = session.execute(
        AimAction(
            fireball.id,
            charmer.position.x + 0.5,
            charmer.position.y + 0.5,
            observation.encounter.decision.id,
        )
    )

    assert result.accepted is True
    assert result.update is not None
    rejection = result.update.events[-1]
    assert rejection.data["success"] is False
    assert rejection.data["reason_code"] == "condition.charmed_target_prohibited"


def test_charmed_reactor_is_not_offered_an_attack_against_the_charmer() -> None:
    session = Session(load_encounter_directory(FULL_CONTROL_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("player")
    player = state.creatures["player"]
    reactor = state.creatures["red_blade"]
    player.position.x, player.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    for index, creature_ref in enumerate(("red_archer", "blue_blade", "blue_archer")):
        state.creatures[creature_ref].position.x = 7 + index
        state.creatures[creature_ref].position.y = 7
    _charm(session, creature_ref="red_blade", source_ref="player")
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )

    choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "player"
    assert state.current_decision().kind == "turn"
    assert reactor.reaction_available is True


def test_new_charm_does_not_consume_an_already_offered_reaction() -> None:
    session = Session(load_encounter_directory(FULL_CONTROL_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("player")
    player = state.creatures["player"]
    reactor = state.creatures["red_blade"]
    player.position.x, player.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    for index, creature_ref in enumerate(("red_archer", "blue_blade", "blue_archer")):
        state.creatures[creature_ref].position.x = 7 + index
        state.creatures[creature_ref].position.y = 7
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    choose_advertised_action(session, move)
    decision = state.current_decision()
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    _charm(session, creature_ref="red_blade", source_ref="player")

    with pytest.raises(ValueError, match="cannot target its charmer"):
        apply_reaction_action(state, opportunity_attack, decision)

    assert reactor.reaction_available is True


def test_charmed_rejects_a_damaging_stat_block_area_over_the_charmer() -> None:
    session = Session(load_encounter_directory(STAT_BLOCK_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("blue_wyrmling")
    state.creatures["breath_target_near"].position.x = 3
    state.creatures["breath_target_near"].position.y = 4
    _charm(
        session,
        creature_ref="blue_wyrmling",
        source_ref="breath_target_near",
    )
    observation = session.observe()
    assert observation.encounter is not None
    breath = next(
        action
        for action in observation.scene.action_details
        if action.kind == "stat_block"
        and action.source_id == "Lightning Breath {@recharge 5}"
    )
    assert breath.enabled is True
    assert breath.required_configuration == "aim"
    charmer = observation.encounter.creature("breath_target_near")

    unconfigured = session.execute(
        SelectAction(
            breath.id,
            observation.encounter.decision.id,
        )
    )
    assert unconfigured.failure is not None
    assert unconfigured.failure.code == "action_configuration_required"
    with pytest.raises(ValueError, match="requires aim configuration"):
        session._choose(breath.id)

    result = session.execute(
        AimAction(
            breath.id,
            charmer.position.x + 0.5,
            charmer.position.y + 0.5,
            observation.encounter.decision.id,
        )
    )

    assert result.accepted is True
    assert result.update is not None
    rejection = result.update.events[-1]
    assert rejection.data["success"] is False
    assert rejection.data["reason_code"] == "condition.charmed_target_prohibited"
