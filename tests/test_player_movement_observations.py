"""Player movement masks use known occupancy; execution uses the actual board."""

from dataclasses import replace
from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.terrain import TerrainCell, TerrainTraversal
from srd_arena.domain.geometry import MovementBudget, Position
from srd_arena.engine.api import SelectAction, Session


def _session(*, hidden: bool = True) -> Session:
    session = Session(
        load_encounter_directory(
            Path("content/encounters/archive/conditions_showcase")
        ),
        seed=42,
    )
    session._read()
    state = session.encounter_state
    assert state is not None
    state.turn.index = state.initiative_order.index("condition_mage")
    state.creatures["condition_mage"].position = Position(0, 0)
    state.creatures["animated_armor"].position = Position(1, 0)
    if hidden:
        state.conditions.append(
            build_applied_condition(
                condition=Condition.INVISIBLE,
                source_ref="animated_armor",
                source_label="Invisibility",
                target_ref="animated_armor",
            )
        )
    return session


def test_hidden_position_does_not_change_movement_rows() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    before = session.observe_player("inflictors")
    assert not before.creature("animated_armor").currently_visible
    state.creatures["animated_armor"].position = Position(5, 0)
    after = session.observe_player("inflictors")
    assert tuple(a for a in before.action_details if a.kind == "move") == tuple(
        a for a in after.action_details if a.kind == "move"
    )


def test_attempt_cannot_enter_hidden_occupant_footprint() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    before = session.observe_player("inflictors")
    action = next(
        a for a in before.action_details if a.id == "condition_mage-move-right"
    )
    assert action.enabled
    budget = state.creatures["condition_mage"].movement_remaining
    result = session.execute_player(
        "inflictors", SelectAction(action.id, before.decision.id)
    )
    assert result.accepted
    assert state.creatures["condition_mage"].position == Position(0, 0)
    assert state.creatures["condition_mage"].movement_remaining == budget
    assert result.update is not None
    assert result.update.messages == ()
    assert result.update.events == ()


def test_visible_occupants_and_grid_edges_still_disable_moves() -> None:
    observation = _session(hidden=False).observe_player("inflictors")
    for direction in ("right", "left", "up"):
        action = next(
            a
            for a in observation.action_details
            if a.id == f"condition_mage-move-{direction}"
        )
        assert not action.enabled


def test_walls_and_movement_budget_still_disable_moves() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    state.definition = replace(
        state.definition,
        terrain=(TerrainCell(Position(1, 0), TerrainTraversal.BLOCKED),),
    )
    observation = session.observe_player("inflictors")
    assert not next(
        a for a in observation.action_details if a.id == "condition_mage-move-right"
    ).enabled
    state.definition = replace(state.definition, terrain=())
    state.creatures["condition_mage"].movement_remaining = MovementBudget(0)
    observation = session.observe_player("inflictors")
    action = next(
        a for a in observation.action_details if a.id == "condition_mage-move-right"
    )
    assert not action.enabled
    assert any(reason.code == "insufficient_movement" for reason in action.reasons)
