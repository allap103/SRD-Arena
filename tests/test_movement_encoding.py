"""Movement semantics survive projection and agree with actual engine steps."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
from srd_arena.domain.encounters.terrain import TerrainCell, TerrainTraversal
from srd_arena.domain.geometry import MovementBudget, Position
from srd_arena.engine.api import ActionObservation, PolicyProjector, Session
from srd_arena.engine.movement_observations import movement_step
from srd_arena.frontends.headless.config import load_policy
from srd_arena.frontends.rl.actions import candidates
from srd_arena.frontends.rl.encoding import ACTION_FEATURES, Encoder
from srd_arena.training.model import CandidatePolicy


@pytest.fixture
def game() -> Session:
    """Place a warlock in open space with a full movement budget."""
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe()
    state = session.encounter_state
    assert state is not None
    state.interrupts.decision_stack.clear()
    state.turn.index = state.initiative_order.index("warlock")
    state.interrupts.decision_stack.append(
        DecisionFrame("movement-test", "warlock", "turn", "test")
    )
    for i, (ref, creature) in enumerate(state.creatures.items()):
        creature.position = (
            Position(3, 3) if ref == "warlock" else Position(8 + i % 3, 6 + i // 3)
        )
    state.creatures["warlock"].movement_remaining = MovementBudget(6)
    return session


def test_all_directions_distinct_independent_of_tokens_and_order(game: Session) -> None:
    """Direction reaches the policy, without action IDs or ordering as features."""
    view = PolicyProjector(
        load_policy(Path("config/observations/minimal.yaml")), "warlock"
    ).project(game.observe_gameplay())
    moves = tuple(a for a in view.action_details if a.kind == "move" and a.enabled)
    assert len(moves) == 8
    view = replace(view, action_details=moves)
    choices = candidates(view)
    encoder = Encoder(view)
    encoded = encoder.encode(view, choices)
    assert len(np.unique(encoded.actions, axis=0)) == 8
    for choice, row in zip(choices, encoded.actions, strict=True):
        movement = choice.movement
        assert movement is not None and movement.destination is not None
        dx, dy = movement.displacement
        assert row[ACTION_FEATURES.index("movement_dx")] == dx
        assert row[ACTION_FEATURES.index("movement_dy")] == dy
        assert row[ACTION_FEATURES.index("movement_destination_x")] == (3 + dx) / 24
        assert row[ACTION_FEATURES.index("movement_destination_y")] == (3 + dy) / 24
        assert row[ACTION_FEATURES.index("movement_cost")] == 1 / 24
        assert row[ACTION_FEATURES.index("movement_cost_known")] == 1
    renamed = replace(
        view,
        action_details=tuple(replace(a, id=f"opaque-{i}") for i, a in enumerate(moves)),
    )
    by_displacement = {
        c.movement.displacement: row
        for c, row in zip(choices, encoded.actions, strict=True)
        if c.movement is not None
    }
    renamed_choices = tuple(reversed(candidates(renamed)))
    reordered = encoder.encode(renamed, renamed_choices)
    for c, row in zip(renamed_choices, reordered.actions, strict=True):
        assert c.movement is not None
        np.testing.assert_array_equal(row, by_displacement[c.movement.displacement])
    torch.manual_seed(7)
    model = CandidatePolicy(8)
    logits, _ = model(encoded)
    assert len(torch.unique(logits)) > 1


@pytest.mark.parametrize("displacement", [(1, 0), (-1, -1)])
@pytest.mark.parametrize("difficult", [False, True])
@pytest.mark.parametrize("prone", [False, True])
def test_advertised_destination_and_cost_match_execution(
    game: Session, displacement: tuple[int, int], difficult: bool, prone: bool
) -> None:
    """Normal and diagonal steps include additive crawling and terrain costs."""
    state = game.encounter_state
    assert state is not None
    dx, dy = displacement
    destination = Position(3 + dx, 3 + dy)
    state.definition = replace(
        state.definition,
        terrain=(TerrainCell(destination, traversal=TerrainTraversal.DIFFICULT),)
        if difficult
        else (),
    )
    if prone:
        apply_condition(
            state,
            build_applied_condition(
                condition=Condition.PRONE,
                source_ref="test",
                source_label="Test fall",
                target_ref="warlock",
            ),
        )
    view = PolicyProjector(
        load_policy(Path("config/observations/training.yaml")), "warlock"
    ).project(game.observe_gameplay())
    choice = next(
        c
        for c in candidates(view)
        if c.movement and c.movement.displacement == displacement
    )
    assert choice.movement is not None
    expected_cost = 1 + int(prone) + int(difficult)
    assert choice.movement.cost == expected_cost
    encoded = Encoder(view).encode(view, (choice,))
    assert (
        encoded.actions[0, ACTION_FEATURES.index("movement_cost")] == expected_cost / 24
    )
    result = game.execute(choice.command)
    assert result.failure is None
    actor = state.creatures["warlock"]
    assert actor.position == destination
    assert actor.movement_remaining == 6 - expected_cost


def test_unknown_movement_data_does_not_become_known_zero(game: Session) -> None:
    """Absent descriptors and destinations keep independent missing indicators."""
    action = ActionObservation(
        "unrelated-id", "Unrelated label", "move", "warlock", movement_direction="up"
    )
    movement = movement_step(action, None)
    assert (
        movement is not None and movement.destination is None and movement.cost is None
    )
    assert movement_step(replace(action, movement_direction=None), None) is None
    view = PolicyProjector(
        load_policy(Path("config/observations/training.yaml")), "warlock"
    ).project(game.observe_gameplay())
    move = next(a for a in view.action_details if a.kind == "move" and a.enabled)
    view = replace(
        view,
        action_details=(
            replace(move, id="known-direction", movement=movement),
            replace(move, id="unknown-direction", movement=None),
        ),
    )
    encoded = Encoder(view).encode(view, candidates(view))
    for name in ("movement_destination_known", "movement_cost_known"):
        assert not encoded.actions[:, ACTION_FEATURES.index(name)].any()
    np.testing.assert_array_equal(
        encoded.actions[:, ACTION_FEATURES.index("movement_displacement_known")], [1, 0]
    )
