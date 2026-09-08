from dataclasses import replace
from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.engine.api import (
    ActionObservation,
    PlayerObservation,
    SelectAction,
    Session,
)

CONDITIONS_SHOWCASE = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "conditions_showcase"
)


def _session() -> Session:
    session = Session(load_encounter_directory(CONDITIONS_SHOWCASE), seed=42)
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("condition_mage")
    return session


def _hold_person_target(
    session: Session,
    target_ref: str,
) -> tuple[PlayerObservation, ActionObservation]:
    observation = session.observe_player("inflictors")
    option = next(
        action
        for action in observation.action_details
        if action.source_id == "hold_person" and action.target_ref == target_ref
    )
    return observation, option


def test_hidden_mechanical_type_does_not_change_player_action_row() -> None:
    session = _session()
    before, before_option = _hold_person_target(session, "animated_armor")
    assert session.encounter_state is not None
    target = session.encounter_state.creatures["animated_armor"].creature
    target.statistics = replace(target.statistics, creature_type="humanoid")

    after, after_option = _hold_person_target(session, "animated_armor")

    assert after.decision == before.decision
    assert after_option == before_option
    assert after_option.enabled is True
    assert after_option.reasons == ()


def test_private_target_failure_is_not_disclosed_after_attempt() -> None:
    session = _session()
    observation, option = _hold_person_target(session, "animated_armor")

    result = session.execute_player(
        "inflictors",
        SelectAction(option.id, observation.decision.id),
    )

    assert result.accepted
    assert result.update is not None
    assert result.update.selected_action_id == option.id
    assert result.update.events == ()
    assert result.update.messages == ()
    assert result.update.observation.decision.id != observation.decision.id
