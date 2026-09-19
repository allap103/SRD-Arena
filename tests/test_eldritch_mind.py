"""Verify Eldritch Mind through the canonical Warlock encounter state."""

from pathlib import Path

import pytest

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.encounters.effect_lifecycle.concentration import (
    resolve_concentration_damage,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.state_runtime import apply_encounter_effects
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    player_first_initiative,
    use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def test_eldritch_mind_grants_advantage_to_a_concentration_save() -> None:
    session = Session(load_encounter_directory(str(WARLOCK_TRAINING_ENCOUNTER_DIR)))
    session._read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "warlock",
                    "source_label": "Warlock",
                    "definition_id": "hideous_laughter",
                },
            )
        ],
        origin_id="hideous-laughter-cast",
    )
    rolls = iter((1, 10))
    use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))
    progress = EncounterProgress()

    resolve_concentration_damage(state, "warlock", 20, progress)

    assert len(state.ongoing_effects) == 1
    event = next(
        event
        for event in progress.events
        if event.type == "concentration_save_resolved"
    )
    assert event.data["dice"] == [1, 10]
    assert event.data["selected_index"] == 1
    assert event.data["mode"] == "advantage"
    assert event.data["success"] is True
    assert event.data["mode_source_ids"] == ["eldritch_mind|xphb"]
