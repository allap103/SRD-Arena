"""Live progress preserves rollout behavior and records real turn boundaries."""

import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session
from srd_arena.training.config import load_training_config
from srd_arena.training.model import CandidatePolicy
from srd_arena.training.progress import EpisodeProgress
from srd_arena.training.train import rollout
from tests.encounter_runtime_support import player_first_initiative


def test_reports_are_throttled_and_flushed(capsys: pytest.CaptureFixture[str]) -> None:
    now = [0.0]
    stream = io.StringIO()
    progress = EpisodeProgress(1, 3, stream, interval=2, clock=lambda: now[0])
    progress.report(force=True)
    now[0] = 1.0
    progress.report("engine")
    assert len(stream.getvalue().splitlines()) == 1
    now[0] = 2.0
    progress.report()
    now[0] = 3.0
    progress.update_total = 5
    progress.report("update", force=True)
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [r["phase"] for r in records] == ["reset", "engine", "update"]
    assert records[-1]["elapsed_seconds"] == 3
    captured = capsys.readouterr()
    assert not captured.out
    assert "Episode 1/3 | 2.0s | engine" in captured.err


@pytest.mark.usefixtures(player_first_initiative.__name__)
def test_reactions_do_not_complete_turns_and_round_changes_do() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    snapshot = session.observe_gameplay()
    encounter = snapshot.game.encounter
    assert encounter is not None and encounter.decision.kind == "turn"
    now = [0.0]
    stream = io.StringIO()
    progress = EpisodeProgress(1, 1, stream, interval=0, clock=lambda: now[0])
    progress.engine_progress(snapshot, 0, 0)
    reaction = replace(
        snapshot,
        game=replace(
            snapshot.game,
            encounter=replace(
                encounter,
                decision=replace(
                    encounter.decision, kind="reaction", creature_ref="goblin_1"
                ),
            ),
        ),
    )
    now[0] = 1
    progress.engine_progress(reaction, 1, 1)
    assert not stream.getvalue()
    now[0] = 2
    # Same creature on a later round is a distinct turn.
    later = replace(
        snapshot,
        game=replace(snapshot.game, encounter=replace(encounter, round_number=2)),
    )
    progress.engine_progress(later, 2, 3)
    progress.engine_progress(later, 2, 3)
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 1
    assert records[0]["event"] == "turn_completed"
    assert records[0]["creature_ref"] == "warlock"
    assert records[0]["turn_seconds"] == 2
    assert records[0]["engine_steps"] == 3


def test_logging_does_not_change_rollout_and_includes_scripted_turns() -> None:
    config = load_training_config(Path("config/training/single_encounter.yaml"))
    model = CandidatePolicy(8)
    plain = config.environment()
    _, expected = rollout(plain, model, seed=42, mode="wait")
    logged = config.environment()
    stream = io.StringIO()
    progress = EpisodeProgress(1, 1, stream, interval=0)
    _, actual = rollout(logged, model, seed=42, mode="wait", progress=progress)
    assert actual.info == expected.info
    assert actual.reward == expected.reward
    assert logged.progress_callback is None
    turns = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert {"warlock", "barbarian", "goblin_3"} <= {r["creature_ref"] for r in turns}
    assert len({(r["round"], r["creature_ref"]) for r in turns}) == len(turns)
    assert turns[-1]["reason"] == "encounter_ended"
    assert all(r["turn_seconds"] >= 0 for r in turns)


@pytest.mark.parametrize("interval", [-1.0, float("nan"), float("inf")])
def test_invalid_progress_interval(interval: float) -> None:
    with pytest.raises(ValueError, match="Progress interval"):
        EpisodeProgress(1, 1, io.StringIO(), interval=interval)
