"""Verify the canonical Barbarian's Rage activation and core combat rules."""

from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.runtime import (
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    OngoingEffectKind,
    RuntimeStateIdentity,
    UntilTurnEnd,
)
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.effect_lifecycle.lifecycle_events import (
    resolve_effect_lifecycle_event,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_end import (
    expire_ongoing_effects_for_turn_end,
)
from srd_arena.domain.encounters.rule_queries import (
    InvocationStartContext,
    apply_damage,
    damage_resistances,
    invocation_prohibitions,
    roll_modifiers,
)
from srd_arena.domain.geometry import Position
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    keep_alert_initiative,
    use_deterministic_dice,
)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _prepared_session() -> Session:
    """Give the canonical Barbarian an externally selectable turn."""

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
    return session


def _use_rage(session: Session) -> None:
    """Select the Barbarian's advertised Rage action."""

    rage = next(
        option
        for option in session._read().action_options
        if option.kind == "feature" and option.label == "Rage"
    )
    session._choose(rage.id)


def _rage_effect(session: Session) -> OngoingEffect:
    """Return the active Rage effect from a prepared session."""

    state = session.encounter_state
    assert state is not None
    return next(
        effect
        for effect in state.ongoing_effects
        if effect.identity.source.definition_id == "rage"
    )


def test_rage_activation_spends_a_use_and_replaces_concentration() -> None:
    """Create feature-sourced state and end any maintained spell."""

    session = _prepared_session()
    state = session.encounter_state
    assert state is not None
    barbarian = state.creatures["barbarian"].creature
    state.ongoing_effects.append(
        OngoingEffect(
            RuntimeStateIdentity(
                "concentration:test",
                EffectSource(
                    EffectSourceKind.SPELL,
                    "test_spell",
                    applied_by_ref="barbarian",
                ),
            ),
            ("barbarian",),
            kind=OngoingEffectKind.CONCENTRATION,
        )
    )

    result = session._choose(
        next(
            option.id
            for option in session._read().action_options
            if option.kind == "feature" and option.label == "Rage"
        )
    )

    rage = _rage_effect(session)
    assert barbarian.feature_uses_remaining["rage"] == 2
    assert state.active_bonus_action_available is False
    assert rage.identity.source.kind is EffectSourceKind.FEATURE
    assert rage.duration == UntilTurnEnd("barbarian", state.round.number + 1)
    assert all(
        effect.kind is not OngoingEffectKind.CONCENTRATION
        for effect in state.ongoing_effects
    )
    assert any(event.type == "feature_used" for event in result.events)
    rage_option = next(
        option
        for option in session._read().action_options
        if option.kind == "feature" and option.label == "Rage"
    )
    assert rage_option.enabled is False
    assert "feature_already_active" in {
        failure.code for failure in rage_option.eligibility.failures
    }


def test_rage_contributes_resistance_advantage_and_spell_prohibition() -> None:
    """Answer shared rule queries from the active Rage effect."""

    session = _prepared_session()
    _use_rage(session)
    state = session.encounter_state
    assert state is not None

    assert damage_resistances(state, "barbarian").values >= {
        "bludgeoning",
        "piercing",
        "slashing",
    }
    barbarian = state.creatures["barbarian"].creature
    initial_health = barbarian.get_health()
    assert apply_damage(state, "barbarian", 9, "slashing") == 4
    assert barbarian.get_health() == initial_health - 4
    assert (
        roll_modifiers(state, "barbarian", "ability_check", "strength").mode
        == "advantage"
    )
    assert (
        roll_modifiers(state, "barbarian", "saving_throw", "strength").mode
        == "advantage"
    )
    dexterity_save = roll_modifiers(
        state,
        "barbarian",
        "saving_throw",
        "dexterity",
    )
    assert dexterity_save.mode == "advantage"
    assert {
        contribution.source.definition_id
        for contribution in dexterity_save.contributions
    } == {"danger_sense"}
    prohibitions = invocation_prohibitions(
        state,
        InvocationStartContext("barbarian", "cast_spell"),
    )
    assert [(failure.code, failure.state_ids) for failure in prohibitions] == [
        ("rage_spellcasting", (_rage_effect(session).identity.id,))
    ]


def test_rage_adds_two_to_strength_based_weapon_damage() -> None:
    """Apply Rage damage to the canonical Barbarian's Maul attack."""

    session = _prepared_session()
    use_deterministic_dice(session, die_roller=lambda _sides: 4)
    _use_rage(session)
    state = session.encounter_state
    assert state is not None
    state.round.number += 1
    state.creatures["barbarian"].features_used_this_turn.add("savage_attacker")
    ogre = state.creatures["ogre_target"].creature
    initial_health = ogre.get_health()
    attack_id = next(
        option.id
        for option in session._read().action_options
        if option.kind == "attack"
        and option.preferred_attack_name == "Maul"
        and option.details is not None
        and getattr(option.details, "target_ref", None) == "ogre_target"
    )

    result = session._choose(attack_id)
    if state.current_decision().kind == "reckless_attack":
        decline = next(
            option
            for option in session._read().action_options
            if option.kind == "decline_reckless_attack"
        )
        result = session._choose(decline.id)

    attack = next(event for event in result.events if event.type == "attack_resolved")
    assert attack.data["damage"] == 14
    damage_detail = attack.data["damage_roll_detail"]
    assert isinstance(damage_detail, dict)
    assert damage_detail["modifier"] == 6
    assert ogre.get_health() == initial_health - 14
    assert _rage_effect(session).duration == UntilTurnEnd("barbarian", 3)


def test_rage_can_be_extended_by_bonus_action_or_forcing_an_enemy_save() -> None:
    """Refresh Rage through both non-attack extension mechanisms."""

    session = _prepared_session()
    _use_rage(session)
    state = session.encounter_state
    assert state is not None
    state.round.number += 1
    state.active_bonus_action_available = True
    extension = next(
        option
        for option in session._read().action_options
        if option.kind == "feature" and option.label == "Extend Rage"
    )

    session._choose(extension.id)

    assert _rage_effect(session).duration == UntilTurnEnd("barbarian", 3)
    assert state.creatures["barbarian"].creature.feature_uses_remaining["rage"] == 2

    state.round.number += 1
    resolve_effect_lifecycle_event(
        state,
        "target_forces_saving_throw",
        actor_ref="barbarian",
        target_ref="goblin_1",
    )
    assert _rage_effect(session).duration == UntilTurnEnd("barbarian", 4)


def test_incapacitation_and_turn_expiry_end_rage() -> None:
    """Remove Rage at either of its currently modeled end boundaries."""

    incapacitated_session = _prepared_session()
    _use_rage(incapacitated_session)
    incapacitated_state = incapacitated_session.encounter_state
    assert incapacitated_state is not None
    apply_condition(
        incapacitated_state,
        build_applied_condition(
            condition=Condition.INCAPACITATED,
            source_ref="test",
            source_label="Test",
            target_ref="barbarian",
        ),
    )
    assert not any(
        effect.identity.source.definition_id == "rage"
        for effect in incapacitated_state.ongoing_effects
    )

    expiry_session = _prepared_session()
    _use_rage(expiry_session)
    expiry_state = expiry_session.encounter_state
    assert expiry_state is not None
    expiry_state.round.number += 1
    expire_ongoing_effects_for_turn_end(expiry_state, "barbarian")
    assert not any(
        effect.identity.source.definition_id == "rage"
        for effect in expiry_state.ongoing_effects
    )
