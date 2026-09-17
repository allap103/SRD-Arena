"""Complete casts validate atomically; GUI draft edits never enter game state."""

from dataclasses import replace
from pathlib import Path

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
from srd_arena.engine.api import CastSpell, PolicyProjector, Session
from srd_arena.frontends.gui.presenter import GamePresenter
from srd_arena.frontends.headless.config import load_policy
from srd_arena.frontends.rl.actions import candidates


def game() -> Session:
    """Place the Warlock at an external decision in the training encounter."""
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe()
    state = session.encounter_state
    assert state is not None
    state.interrupts.decision_stack[:] = [
        DecisionFrame("cast-test", "warlock", "turn", "test")
    ]
    state.turn.index = state.initiative_order.index("warlock")
    return session


def cast(session: Session, refs: tuple[str, ...]) -> CastSpell:
    """Build an Eldritch Blast with an explicit ordered beam assignment."""
    view = session.observe()
    assert view.encounter is not None
    option = next(
        a
        for a in view.scene.action_details
        if a.source_id == "eldritch_blast" and a.enabled
    )
    return CastSpell(option.id, view.encounter.decision.id, refs)


@pytest.mark.parametrize(
    "refs", [(), ("goblin_1",), ("goblin_1",) * 3, ("missing", "goblin_1")]
)
def test_invalid_complete_cast_is_atomic(refs: tuple[str, ...]) -> None:
    session = game()
    command = cast(session, refs)
    before = session.observe_gameplay()
    result = session.execute(command)
    assert not result.accepted
    assert session.observe_gameplay() == before


def test_complete_cast_never_opens_target_selection() -> None:
    session = game()
    result = session.execute(cast(session, ("goblin_1", "goblin_2")))
    assert result.accepted, result.failure
    state = session.encounter_state
    assert state is not None
    assert not hasattr(state.interrupts, "pending_spell_cast")
    assert state.current_decision().kind != "spell_targets"
    assert state.current_decision().kind == "d20_roll_modifier"


def test_gui_target_edits_and_cancel_leave_engine_unchanged() -> None:
    session = game()
    presenter = GamePresenter(session)
    command = cast(session, ("goblin_1", "goblin_2"))
    before = session.observe_gameplay()
    assert presenter.select_action(command.action_id) is not None
    assert presenter.observation.encounter is not None
    assert presenter.observation.encounter.targeting is not None
    assert session.observe_gameplay() == before
    # Edits are entirely local, including cancellation.
    assert presenter.cancel_targeting() is not None
    assert session.observe_gameplay() == before


def test_gui_complete_selection_submits_a_single_cast() -> None:
    session = game()
    presenter = GamePresenter(session)
    command = cast(session, ("goblin_1", "goblin_2"))
    option = next(
        a
        for a in presenter.observation.scene.action_details
        if a.id == command.action_id
    )
    assert presenter.select_action(command.action_id) is not None
    # Completing the second beam auto-confirms in the GUI.
    result = presenter.change_target(
        "goblin_2", remove=False, source_trigger_id=option.source_id
    )
    assert result is not None
    assert session.encounter_state is not None
    assert session.encounter_state.current_decision().kind != "spell_targets"
    assert session.encounter_state.current_decision().kind == "d20_roll_modifier"


def test_model_candidates_include_full_beam_sequences() -> None:
    session = game()
    view = PolicyProjector(
        load_policy(Path("config/observations/training.yaml")), "warlock"
    ).project(session.observe_gameplay())
    choices = candidates(view)
    beams = [c for c in choices if c.spell and c.spell.spell_id == "eldritch_blast"]
    assert beams
    from srd_arena.frontends.rl.spell_candidates import preparation_choices

    completed = [
        child for base in beams for child in preparation_choices(base, maximum=100)
    ]
    assert all(
        isinstance(c.command, CastSpell) and len(c.selected_refs) == 2
        for c in completed
    )
    assert any(c.selected_refs == ("goblin_1", "goblin_2") for c in completed)
    assert any(c.selected_refs == ("goblin_2", "goblin_1") for c in completed)
    assert all(
        c.kind not in {"toggle_spell_target", "confirm_spell_targets"} for c in choices
    )


def test_stale_complete_cast_and_malformed_allocations_are_rejected() -> None:
    session = game()
    command = cast(session, ("goblin_1", "goblin_2"))
    assert not session.execute(replace(command, expected_decision_id="old")).accepted
    assert not session.execute(
        replace(command, allocations=(("goblin_1", 1),))
    ).accepted


def test_local_model_preparation_does_not_advance_engine() -> None:
    from srd_arena.training.config import load_training_config

    env = load_training_config(
        Path("config/training/goblin_pressure.yaml")
    ).environment()
    transition = env.reset(seed=42)
    while not any(
        c.spell and c.spell.spell_id == "eldritch_blast" for c in env.choices
    ):
        index = next(
            i
            for i, c in enumerate(env.choices)
            if c.kind.startswith("decline_") or c.kind == "keep_initiative"
        )
        transition = env.step(index)
    index = next(
        i
        for i, c in enumerate(env.choices)
        if c.spell and c.spell.spell_id == "eldritch_blast"
    )
    before = env.spectator_snapshot()
    previous_count = transition.info["decisions"]
    assert isinstance(previous_count, int)
    prepared = env.prepare_action(index, lambda encoded, choices: 0)
    assert len(prepared.selected_refs) == 2
    assert env.spectator_snapshot() == before
    end = env.step(prepared, expected_decision_id=transition.decision_id)
    assert end.info["decisions"] == previous_count + 1
    assert not end.info["rejection"]


def test_encoder_distinguishes_ordered_beams_and_resource_amounts() -> None:
    import numpy as np

    from srd_arena.frontends.rl.encoding import Encoder
    from srd_arena.frontends.rl.spell_candidates import preparation_choices

    session = game()
    view = PolicyProjector(
        load_policy(Path("config/observations/training.yaml")), "warlock"
    ).project(session.observe_gameplay())
    beams = [
        c for c in candidates(view) if c.spell and c.spell.spell_id == "eldritch_blast"
    ]
    completed = [
        child for base in beams for child in preparation_choices(base, maximum=100)
    ]
    a = next(c for c in completed if c.selected_refs == ("goblin_1", "goblin_2"))
    b = next(c for c in completed if c.selected_refs == ("goblin_2", "goblin_1"))
    encoded = Encoder(view).encode(
        view, (a, b, replace(a, allocations=(("goblin_1", 3),)))
    )
    assert np.array_equal(
        encoded.selected_entity_weights[0, 0], encoded.selected_entity_weights[1, 0]
    )
    assert not np.array_equal(
        encoded.selected_entity_weights[0, 1], encoded.selected_entity_weights[1, 1]
    )
    assert not np.array_equal(
        encoded.selected_entity_weights[0, 2], encoded.selected_entity_weights[2, 2]
    )


def test_complete_area_cast_cannot_override_occupants() -> None:
    session = game()
    view = session.observe()
    assert view.encounter is not None
    action = next(
        a for a in view.scene.action_details if a.source_id == "fireball" and a.enabled
    )
    before = session.observe_gameplay()
    result = session.execute(
        CastSpell(action.id, view.encounter.decision.id, ("goblin_1",), aim=(2, 1))
    )
    assert not result.accepted
    assert session.observe_gameplay() == before


def test_old_target_edit_protocol_is_not_an_engine_command() -> None:
    from srd_arena.frontends.headless.cli import parse_command

    with pytest.raises(ValueError, match="Unknown command"):
        parse_command(
            '{"type":"command","command":"change_target","expected_decision_id":"d","target_ref":"goblin_1","remove":false}'
        )
