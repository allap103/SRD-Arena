"""Verify the deterministic policy used by the fixed Barbarian ally."""

from pathlib import Path
from unittest.mock import Mock, patch

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.decisions import (
    RecklessAttackRequest,
)
from srd_arena.domain.encounters.scripted_policies import (
    BarbarianAllyActionSelector,
)
from srd_arena.domain.geometry import MovementBudget, Position
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import keep_alert_initiative

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _prepared_session() -> Session:
    """Start a deterministic Barbarian turn beside the training Ogre."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    state.turn.index = state.initiative_order.index("barbarian")
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(5, 4)
    state.creatures["warlock"].position = Position(0, 0)
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position = Position(9, index * 2)
    return session


def test_training_barbarian_uses_the_dedicated_selector() -> None:
    """Select the fixed ally policy from authored encounter behavior."""

    session = _prepared_session()
    state = session.encounter_state
    assert state is not None

    assert isinstance(
        state._action_selectors["barbarian"],
        BarbarianAllyActionSelector,
    )


def test_barbarian_policy_conserves_rage_without_an_opponent() -> None:
    """Wait instead of spending Rage when no living enemy remains."""

    selector = BarbarianAllyActionSelector()
    state = Mock()
    state.current_decision.return_value.kind = "turn"
    actions = (
        EncounterAction("Rage", "feature", "rage"),
        EncounterAction("Wait", "wait"),
    )

    with patch(
        "srd_arena.domain.encounters.scripted_policies.barbarian.living_creature_refs",
        return_value=[],
    ):
        selected = selector.select_action(state, "barbarian", actions)

    assert selected.kind == "wait"


def test_barbarian_policy_attacks_its_web_without_a_living_opponent() -> None:
    """Remove a persistent attachment instead of waiting for an opponent."""

    selector = BarbarianAllyActionSelector()
    state = Mock()
    state.current_decision.return_value.kind = "turn"
    actions = (
        EncounterAction(
            "Attack Web - Maul",
            "attack_condition",
            "barbarian",
            preferred_attack_type="melee",
            preferred_attack_name="Maul",
        ),
        EncounterAction("Wait", "wait"),
    )

    selected = selector.select_action(state, "barbarian", actions)

    assert selected.kind == "attack_condition"
    assert selected.preferred_attack_name == "Maul"


def test_barbarian_policy_uses_free_rage_extension_before_pursuit() -> None:
    """Keep an active Rage alive before spending movement or an Action."""

    selector = BarbarianAllyActionSelector()
    state = Mock()
    state.current_decision.return_value.kind = "turn"
    actions = (
        EncounterAction("Extend Rage", "feature", "extend_rage"),
        EncounterAction("Wait", "wait"),
    )

    with patch(
        "srd_arena.domain.encounters.scripted_policies.barbarian._nearest_opponent",
        return_value="enemy",
    ):
        selected = selector.select_action(state, "barbarian", actions)

    assert selected.value == "extend_rage"


def test_barbarian_policy_starts_rage_before_attacking_recklessly() -> None:
    """Use Rage, choose the Maul, and accept the first-roll Reckless choice."""

    session = _prepared_session()
    state = session.encounter_state
    assert state is not None

    rage = session.advance_one_automatic_action()

    assert any(event.type == "feature_used" for event in rage.events)
    assert any(
        effect.identity.source.definition_id == "rage"
        for effect in state.ongoing_effects
    )

    selector = state._action_selectors["barbarian"]
    available = available_creature_actions(
        state,
        "barbarian",
        include_attack_alternatives=True,
    )
    selected = selector.select_action(state, "barbarian", tuple(available))
    assert selected is not None
    assert selected.preferred_attack_name == "Maul"

    attack = session.advance_one_automatic_action()

    decision = state.current_decision()
    assert decision.kind == "reckless_attack"
    assert isinstance(decision.request, RecklessAttackRequest)
    assert any(
        event.type == "decision_opened" and event.data.get("kind") == "reckless_attack"
        for event in attack.events
    )

    reckless = session.advance_one_automatic_action()

    assert any(
        event.type == "reckless_attack_resolved" and event.data.get("used") is True
        for event in reckless.events
    )


def test_barbarian_policy_moves_before_using_its_ranged_fallback() -> None:
    """Follow a legal shortest route while movement remains."""

    session = _prepared_session()
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["barbarian"]
    actor.bonus_action_available = False
    actor.position = Position(2, 4)
    state.creatures["ogre_target"].position = Position(8, 4)
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position = Position(10, index * 3)
    selector = state._action_selectors["barbarian"]
    actions = available_creature_actions(
        state,
        "barbarian",
        include_attack_alternatives=True,
    )

    selected = selector.select_action(state, "barbarian", tuple(actions))

    assert selected is not None
    assert selected.kind == "move"


def test_barbarian_policy_uses_javelin_after_exhausting_movement() -> None:
    """Retain a deterministic ranged fallback when melee cannot be reached."""

    session = _prepared_session()
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["barbarian"]
    actor.bonus_action_available = False
    actor.movement_remaining = MovementBudget(0)
    actor.position = Position(2, 4)
    state.creatures["ogre_target"].position = Position(8, 4)
    for index, target_ref in enumerate(("goblin_1", "goblin_2", "goblin_3")):
        state.creatures[target_ref].position = Position(10, index * 3)
    selector = state._action_selectors["barbarian"]
    actions = available_creature_actions(
        state,
        "barbarian",
        include_attack_alternatives=True,
    )

    selected = selector.select_action(state, "barbarian", tuple(actions))

    assert selected is not None
    assert selected.kind == "attack"
    assert selected.preferred_attack_type == "ranged"
    assert selected.preferred_attack_name == "Javelin"
