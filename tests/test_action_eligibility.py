from pathlib import Path

from srd_arena.domain.actions.eligibility import evaluate_action
from srd_arena.domain.actions.pipeline import (
    ActionExecutionContext,
    ActionPipeline,
)
from srd_arena.domain.effects.conditions import Status
from srd_arena.domain.encounters.behaviors import DIRECTION_DELTAS
from srd_arena.domain.encounters.models import EncounterAction
from srd_arena.domain.geometry import Position
from srd_arena.runtime.scenario import ScenarioLoader

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def _player_session():
    session = (
        ScenarioLoader()
        .load(FIXTURE_ENCOUNTER_DIR)
        .create_session()
        .start_encounter()
    )
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn_index = state.initiative_order.index("player")
    state.decision_stack.clear()
    return session, state


def test_incapacitating_condition_uses_shared_eligibility_rule() -> None:
    session, state = _player_session()
    state.conditions.append(
        Status(
            id="stunned:test:player",
            name="stunned",
            source_ref="enemy:0",
            source_label="Enemy",
            target_ref="player",
        )
    )

    attack = EncounterAction(
        "Attack",
        "attack",
        0,
        id="test-attack",
        actor_ref="player",
    )
    result = evaluate_action(state, session.player, attack)
    available_kinds = {
        action.kind for action in state.actions.available(session.player)
    }

    assert result.allowed is False
    assert result.primary_reason == "You cannot take that action while stunned."
    assert available_kinds == {"wait"}


def test_execution_revalidates_action_after_state_changes() -> None:
    session, state = _player_session()
    move = next(
        action
        for action in state.actions.available(session.player)
        if action.kind == "move"
    )
    assert isinstance(move.value, str)
    dx, dy = DIRECTION_DELTAS[move.value]
    state.enemies[0].position = Position(
        state.player_position.x + dx,
        state.player_position.y + dy,
    )

    result = session.choose_encounter_action(move)

    assert result.messages == [("system", "You cannot move there.")]
    assert [event.type for event in result.events] == ["action_rejected"]


def test_pipeline_declares_action_before_calling_resolver() -> None:
    session, state = _player_session()
    move = next(
        action
        for action in state.actions.available(session.player)
        if action.kind == "move"
    )
    observed_events: list[str] = []

    def resolve(context: ActionExecutionContext) -> None:
        observed_events.extend(event.type for event in context.progress.events)
        assert context.action_id is not None
        context.progress.events.append(
            context.state._event(
                "action_resolved",
                actor_ref=context.action.actor_ref,
                action_id=context.action_id,
            )
        )

    result = ActionPipeline().execute(state, session.player, move, resolve)

    assert observed_events == ["action_declared"]
    assert [event.type for event in result.events] == [
        "action_declared",
        "action_resolved",
    ]
    assert result.events[0].action_id == result.events[1].action_id


def test_ai_action_uses_same_declare_then_resolve_pipeline() -> None:
    session, state = _player_session()
    state.turn_index = state.initiative_order.index("enemy:0")

    _completed, progress, actions_resolved = state._run_enemy_turn(
        session.player,
        0,
        action_limit=1,
    )

    assert actions_resolved == 1
    assert progress.events[0].type == "action_declared"
    assert progress.events[1].type in {"movement_resolved", "attack_resolved"}
    assert progress.events[0].action_id == progress.events[1].action_id
