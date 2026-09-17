from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.engine.api import (
    ActionObservation,
    PlayerObservation,
    SelectAction,
    Session,
    SpellCastOptions,
)
from srd_arena.engine.commands import (
    AimAction,
    CastSpell,
    CommandFailure,
    CommandResult,
    GameCommand,
)
from srd_arena.engine.player_interactions import _configuration_is_advertised

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


@pytest.mark.parametrize(
    "command",
    [
        SelectAction("guessed", "current"),
        AimAction("guessed", 1, 1, "current"),
        CastSpell("guessed", "current", ("animated_armor",)),
    ],
)
def test_every_player_command_requires_decision_ownership(command: GameCommand) -> None:
    session = _session()
    before = session.observe_player("resisters")
    result = session.execute_player(
        "resisters", replace(command, expected_decision_id=before.decision.id)
    )
    assert result.failure is not None
    assert result.failure.code == "decision_not_owned"
    assert session.observe_player("resisters") == before


@pytest.mark.parametrize(
    ("command", "option"),
    [
        (
            AimAction("aim", 1, 1, "current"),
            ActionObservation(
                "aim", "Aim", "spell", "condition_mage", required_configuration="aim"
            ),
        ),
        (
            CastSpell("cast", "current", ("condition_mage",)),
            ActionObservation(
                "cast",
                "Cast",
                "spell",
                "condition_mage",
                spell_cast=SpellCastOptions(
                    ("condition_mage",), ("condition_mage",), 1, False, False, True
                ),
            ),
        ),
    ],
)
def test_configuration_requires_an_enabled_public_option(
    command: GameCommand,
    option: ActionObservation,
) -> None:
    observation = _session().observe_player("inflictors")
    assert _configuration_is_advertised(
        replace(observation, action_details=(option,)), command
    )
    assert not _configuration_is_advertised(
        replace(observation, action_details=()), command
    )
    assert not _configuration_is_advertised(
        replace(observation, action_details=(replace(option, enabled=False),)), command
    )
    session = _session()
    current = session.observe_player("inflictors")
    command = replace(command, expected_decision_id=current.decision.id)
    with (
        patch.object(
            session, "observe_player", return_value=replace(current, action_details=())
        ),
        patch("srd_arena.engine.player_interactions.execute_game_command") as execute,
    ):
        result = session.execute_player("inflictors", command)
        assert result.failure is not None
        assert result.failure.code == "action_unavailable"
        execute.assert_not_called()
    with (
        patch.object(
            session,
            "observe_player",
            return_value=replace(current, action_details=(option,)),
        ),
        patch(
            "srd_arena.engine.player_interactions.execute_game_command",
            return_value=CommandResult(
                failure=CommandFailure("private", "Hidden target statistic")
            ),
        ) as execute,
    ):
        result = session.execute_player("inflictors", command)
        execute.assert_called_once_with(session, command)
        assert result.failure is not None
        assert result.failure.code == "command_rejected"
        assert "Hidden" not in result.failure.message


def test_configuration_rejects_unadvertised_targets_and_enemy_allocation() -> None:
    observation = _session().observe_player("inflictors")
    option = ActionObservation(
        "cast",
        "Cast",
        "spell",
        "condition_mage",
        spell_cast=SpellCastOptions(("animated_armor",), (), 1, False, False, True),
    )
    view = replace(observation, action_details=(option,))
    assert not _configuration_is_advertised(
        view, CastSpell("cast", view.decision.id, ("missing",))
    )
    assert not _configuration_is_advertised(
        view,
        CastSpell(
            "cast", view.decision.id, ("animated_armor",), (("animated_armor", 1),)
        ),
    )
